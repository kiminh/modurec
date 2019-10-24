import os

import time

import pandas as pd
import numpy as np
import torch
from torch import optim
import torch.nn.functional as F

from grecom.data_utils import create_recom_data
from grecom.model import RecomNet, GAENet
from grecom.parser import parser_recommender
from grecom.utils import common_processing, EarlyStopping

from sklearn.model_selection import train_test_split

TOY = False
verbose = False


def train_recom_net(recom_data, args):
    n_ratings = len(recom_data.rating_graph.edge_index[0]) // 2
    train_mask, val_mask = train_test_split(np.array(range(n_ratings)), test_size=0.2, random_state=1)
    val_mask, test_mask = train_test_split(val_mask, test_size=0.5, random_state=1)

    params = {
        'edge_sim': recom_data.similar_graph.edge_index.to(args.device),
        'edge_rat': recom_data.rating_graph.edge_index.to(args.device),
        'x': recom_data.similar_graph.x.to(args.device),
        'ratings': recom_data.ratings.iloc[train_mask],
        'args': args
    }
    model = RecomNet(**params)
    optimizer = optim.Adam(model.parameters(), args.lr, weight_decay=5e-4)
    if args.early_stopping:
        earlyS = EarlyStopping(mode='min', patience=args.early_stopping)

    results = pd.DataFrame()
    epoch_size = len(train_mask)  # // 4 + 1
    for epoch in range(args.epochs):
        t0 = time.time()
        # Training
        model.train()
        batch_size = epoch_size
        training_loss = 0
        for n_batch, i in enumerate(range(0, epoch_size, batch_size)):
            optimizer.zero_grad()
            train_batch = train_mask[i:i + batch_size]
            pred_rating = model(train_batch)
            real_rating = torch.tensor(recom_data.ratings.rating.iloc[train_batch].values, dtype=torch.float).to(args.device)
            train_loss = F.mse_loss(pred_rating, real_rating)
            train_loss.backward()
            training_loss += train_loss
            optimizer.step()
        training_loss /= (n_batch + 1)
        # Validation
        model.eval()
        with torch.no_grad():
            pred_rating = model(val_mask)
            real_rating = torch.tensor(recom_data.ratings.rating.iloc[val_mask].values, dtype=torch.float).to(args.device)
            val_loss = F.mse_loss(pred_rating, real_rating)
            if args.early_stopping:
                if earlyS.step(val_loss.cpu().numpy()):
                    break
            results = results.append(
                {'epoch': epoch,
                 'train_rmse': np.sqrt(training_loss),
                 'val_rmse': np.sqrt(val_loss.item())},
                ignore_index=True)
        print(f"Epoch: {epoch}  --- train_mse={np.sqrt(training_loss):.3f}, "
              f"val_rmse={np.sqrt(val_loss.item()):.3f}, time={time.time() - t0:.2f}")
    return model, results


def train_gae_net(recom_data, args):
    # Create masks
    non_zero = np.where(recom_data.rating_matrix != 0)
    train_inds, val_inds = train_test_split(np.array(non_zero).T, test_size=0.2, random_state=1)
    val_inds, test_inds = train_test_split(val_inds, test_size=0.5, random_state=1)

    train_mask = np.zeros_like(recom_data.rating_matrix)
    train_mask[tuple(train_inds.T)] = 1
    val_mask = np.zeros_like(recom_data.rating_matrix)
    val_mask[tuple(val_inds.T)] = 1
    model = GAENet(recom_data, train_mask, val_mask, args)
    optimizer = optim.Adam(model.parameters(), args.lr)
    scheduler = optim.lr_scheduler.StepLR(optimizer, step_size=50, gamma=0.96)
    results = pd.DataFrame()
    for epoch in range(1000):
        t0 = time.time()
        # Training
        model.train()
        batch_size = recom_data.n_users
        batch_inds = np.random.permutation(list(range(recom_data.n_users)))
        for i in range(0, recom_data.n_users, batch_size):
            optimizer.zero_grad()
            batch = batch_inds[i:i + batch_size]
            real, pred, reg_loss = model(batch, train='user')
            mse_loss = F.mse_loss(real[real != 0], pred[real != 0])
            train_loss = mse_loss + reg_loss
            train_loss.backward()
            optimizer.step()
        batch_size = recom_data.n_items
        batch_inds = np.random.permutation(list(range(recom_data.n_items)))
        for i in range(0, recom_data.n_items, batch_size):
            optimizer.zero_grad()
            batch = batch_inds[i:i + batch_size]
            real, pred, reg_loss = model(batch, train='item')
            mse_loss = F.mse_loss(real[real != 0], pred[real != 0])
            train_loss = mse_loss + reg_loss
            train_loss.backward()
            optimizer.step()
        # Validation
        model.eval()
        with torch.no_grad():
            real_train, real_val = model.x_train, model.x_val
            pred, p_u, p_v = model(is_val=True)
            train_loss = F.mse_loss(real_train[real_train != 0], pred[real_train != 0])
            val_loss = F.mse_loss(real_val[real_val != 0], pred[real_val != 0])
            results = results.append(
                {'epoch': epoch,
                 'train_rmse': train_loss.item() ** (1/2),
                 'val_rmse': val_loss.item() ** (1/2)},
                ignore_index=True)
            print(f"(u+v) Epoch: {epoch}  --- train_rmse={train_loss.item() ** (1/2):.3f}, "
                  f"val_rmse={val_loss.item() ** (1/2):.3f}, time={time.time() - t0:.2f}")
            train_loss = F.mse_loss(real_train[real_train != 0], p_u[real_train != 0])
            val_loss = F.mse_loss(real_val[real_val != 0], p_u[real_val != 0])
            print(f"( u ) Epoch: {epoch}  --- train_rmse={train_loss.item() ** (1 / 2):.3f}, "
                  f"val_rmse={val_loss.item() ** (1 / 2):.3f}")
            train_loss = F.mse_loss(real_train[real_train != 0], p_v[real_train != 0])
            val_loss = F.mse_loss(real_val[real_val != 0], p_v[real_val != 0])
            print(f"( v ) Epoch: {epoch}  --- train_rmse={train_loss.item() ** (1 / 2):.3f}, "
                  f"val_rmse={val_loss.item() ** (1 / 2):.3f}")
        scheduler.step()
    return model, results


def train():
    args = parser_recommender()
    args = common_processing(args)
    torch.set_num_threads(6)

    # Load graph
    recom_data = create_recom_data(args, is_toy=TOY)

    params = {
        'recom_data': recom_data,
        'args': args
    }
    if args.model == 'hetero_gcmc':
        model, results = train_recom_net(**params)
    elif args.model == 'gautorec':
        model, results = train_gae_net(**params)
    else:
        raise ValueError

    # Save models
    torch.save(model.state_dict(), os.path.join(args.models_path, 'recom_model.pt'))

    # Save results
    results.to_hdf(os.path.join(args.results_path, 'results.h5'), 'results', mode='w')


if __name__ == "__main__":
    train()