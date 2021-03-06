import torch
import torch.nn as nn

from grecom.layers import ContentFiltering, FeatureCombiner, FeatureCombiner_scal, FilmLayer, GraphConv0D, GraphConv0D_adaptive, TimeNN, TimeNN1L

model_params = {'hidden_size': 500,
                'dropout_input': 0.7,
                'dropout_emb': 0.5}


class Autorec(nn.Module):
    requires_time = False
    requires_fts = False
    requires_graph = False

    def __init__(self, args, input_size, rating_range=(1, 5), model_params=model_params):
        super(Autorec, self).__init__()
        self.args = args
        hidden = model_params['hidden_size']
        self.encoder = nn.Linear(input_size, hidden)
        self.sig_act = nn.Sigmoid()
        self.decoder = nn.Linear(hidden, input_size)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

    def forward(self, x, ft_n):
        x = self.sig_act(self.encoder(x))
        p = self.decoder(x)
        if not self.training:
            p = self.limiter(p)
            p[torch.nonzero(ft_n[0] == 0), :] = ft_n[2]
            p[:, torch.nonzero(ft_n[1] == 0)] = ft_n[2]
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        return reg_loss


class Autorec_D(nn.Module):
    requires_time = False
    requires_fts = False
    requires_graph = False

    def __init__(self, args, input_size, rating_range=(1, 5)):
        super(Autorec_D, self).__init__()
        self.args = args

        self.dropout_input = nn.Dropout(model_params['dropout_input'])
        self.encoder = nn.Linear(input_size, model_params['hidden_size'])
        self.sig_act = nn.Sigmoid()
        self.dropout_emb = nn.Dropout(model_params['dropout_emb'])
        self.decoder = nn.Linear(model_params['hidden_size'], input_size)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

    def forward(self, x, ft_n):
        x = self.dropout_input(x)
        x = self.sig_act(self.encoder(x))
        x = self.dropout_emb(x)
        p = self.decoder(x)
        if not self.training:
            p = self.limiter(p)
            p[torch.nonzero(ft_n[0] == 0), :] = ft_n[2]
            p[:, torch.nonzero(ft_n[1] == 0)] = ft_n[2]
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        return reg_loss


class Autorec_DF(nn.Module):
    requires_time = False
    requires_fts = True
    requires_graph = False

    def __init__(self, args, input_size, rating_range=(1, 5)):
        super(Autorec_DF, self).__init__()
        self.args = args

        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

        self.ft_model = ContentFiltering(args, ft_size)
        self.ft_comb = FeatureCombiner(args)

    def forward(self, x, ft_n, ft_x):
        hf = self.ft_model(ft_x)
        h = self.ft_comb(x, hf, ft_n)
        x = self.dropout_input(x)
        x = self.sig_act(self.encoder(x))
        x = self.dropout_emb(x)
        p = self.decoder(x)
        if not self.training:
            p = self.limiter(p)
            p[torch.nonzero(ft_n[0] == 0), :] = ft_n[2]
            p[:, torch.nonzero(ft_n[1] == 0)] = ft_n[2]
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.ft_model.get_reg_loss()
        return reg_loss


class Autorec_DG(nn.Module):
    requires_time = False
    requires_fts = False
    requires_graph = True

    def __init__(self, args, input_size, rating_range=(1, 5)):
        super().__init__()
        self.args = args

        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.conv = GraphConv0D(args).to(args.device)
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

    def forward(self, x, ft_n, graph):
        graph = graph[0]
        x = self.dropout_input(x)
        x = self.sig_act(self.encoder(x))
        x = self.conv(x, graph['edge_index'], graph['edge_weight'])
        x = self.dropout_emb(x)
        p = self.decoder(x)
        if not self.training:
            p = self.limiter(p)
            p[torch.nonzero(ft_n[0] == 0), :] = ft_n[2]
            p[:, torch.nonzero(ft_n[1] == 0)] = ft_n[2]
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        return reg_loss


class Autorec_DT(nn.Module):
    requires_time = True
    requires_fts = False
    requires_graph = False

    def __init__(self, args, input_size, rating_range=(1, 5)):
        super(Autorec_DT, self).__init__()
        self.args = args
        self.time_nn = TimeNN(args, n_time_inputs=2)
        self.film_time = FilmLayer(args)
        self.dropout_input = nn.Dropout(model_params['dropout_input'])
        self.encoder = nn.Linear(input_size, model_params['hidden_size'])
        self.sig_act = nn.Sigmoid()
        self.dropout_emb = nn.Dropout(model_params['dropout_emb'])
        self.decoder = nn.Linear(model_params['hidden_size'], input_size)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

    def forward(self, x, ft_n, time_x):
        time_x = self.time_nn(time_x[..., :2])
        time_x = time_x * (x > 0)
        x = self.film_time(x, time_x)
        x = self.dropout_input(x)
        x = self.sig_act(self.encoder(x))
        x = self.dropout_emb(x)
        p = self.decoder(x)
        if not self.training:
            p = self.limiter(p)
            p[torch.nonzero(ft_n[0] == 0), :] = ft_n[2]
            p[:, torch.nonzero(ft_n[1] == 0)] = ft_n[2]
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.time_nn.get_reg_loss()
        return reg_loss


class Autorec_DGT(nn.Module):
    requires_time = True
    requires_fts = False
    requires_graph = True

    def __init__(self, args, input_size, rating_range=(1, 5)):
        super().__init__()
        self.args = args

        self.time_nn = TimeNN1L(args, n_time_inputs=2)
        self.film_time = FilmLayer(args)
        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.conv = GraphConv0D(args).to(args.device)
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

    def forward(self, x, ft_n, time_x, graph):
        graph = graph[0]
        time_x = self.time_nn(time_x[...,:2])
        time_x = time_x * (x > 0)
        x = self.film_time(x, time_x)
        x = self.dropout_input(x)
        x = self.sig_act(self.encoder(x))
        x = self.conv(x, graph['edge_index'], graph['edge_weight'])
        x = self.dropout_emb(x)
        p = self.decoder(x)
        if not self.training:
            p = self.limiter(p)
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.time_nn.get_reg_loss()
        return reg_loss


class Autorec_DGT_adap(nn.Module):
    requires_time = True
    requires_fts = False
    requires_graph = True

    def __init__(self, args, input_size, rating_range=(1, 5)):
        super().__init__()
        self.args = args

        self.time_nn = TimeNN1L(args, n_time_inputs=2)
        self.film_time = FilmLayer(args)
        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.conv = GraphConv0D_adaptive(args).to(args.device)
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

    def forward(self, x, ft_n, time_x, graph):
        graph = graph[0]
        time_x = self.time_nn(time_x[...,:2])
        time_x = time_x * (x > 0)
        x = self.film_time(x, time_x)
        x = self.dropout_input(x)
        x = self.sig_act(self.encoder(x))
        x = self.conv(x, ft_n, graph['edge_index'], graph['edge_weight'])
        x = self.dropout_emb(x)
        p = self.decoder(x)
        if not self.training:
            p = self.limiter(p)
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.time_nn.get_reg_loss()
        return reg_loss


class Autorec_DFT_scal(nn.Module):
    requires_time = True
    requires_fts = True
    requires_graph = False

    def __init__(self, args, input_size, ft_size, rating_range=(1, 5)):
        super(Autorec_DFT_scal, self).__init__()
        self.args = args

        self.time_nn = TimeNN1L(args, n_time_inputs=3)
        self.film_time = FilmLayer(args)
        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

        self.ft_model = ContentFiltering(args, ft_size)
        self.ft_comb = FeatureCombiner_scal(args)

    def forward(self, x, time_x, ft_x, ft_n):
        time_x = self.time_nn(time_x)
        time_x = time_x * (x > 0)
        h = self.film_time(x, time_x)
        hf = self.ft_model(ft_x)
        h = self.ft_comb(h, hf, ft_n)
        h = self.dropout_input(h)
        h = self.sig_act(self.encoder(h))
        h = self.dropout_emb(h)
        p = self.decoder(h)
        if not self.training:
            p = self.limiter(p)
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.time_nn.get_reg_loss()
        reg_loss += self.ft_model.get_reg_loss()
        return reg_loss


class Autorec_DFT(nn.Module):
    requires_time = True
    requires_fts = True
    requires_graph = False

    def __init__(self, args, input_size, ft_size, rating_range=(1, 5)):
        super(Autorec_DFT, self).__init__()
        self.args = args

        self.time_nn = TimeNN(args, n_time_inputs=3)
        self.film_time = FilmLayer(args)
        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

        self.ft_model = ContentFiltering(args, ft_size)
        self.ft_comb = FeatureCombiner(args)

    def forward(self, x, time_x, ft_x, ft_n):
        time_x = self.time_nn(time_x)
        time_x = time_x * (x > 0)
        h = self.film_time(x, time_x)
        hf = self.ft_model(ft_x)
        h = self.ft_comb(h, hf, ft_n)
        h = self.dropout_input(h)
        h = self.sig_act(self.encoder(h))
        h = self.dropout_emb(h)
        p = self.decoder(h)
        if not self.training:
            p = self.limiter(p)
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.time_nn.get_reg_loss()
        reg_loss += self.ft_model.get_reg_loss()
        return reg_loss


class Autorec_DFT1L(nn.Module):
    requires_time = True
    requires_fts = True
    requires_graph = False

    def __init__(self, args, input_size, ft_size, rating_range=(1, 5)):
        super().__init__()
        self.args = args

        self.time_nn = TimeNN1L(args, n_time_inputs=3)
        self.film_time = FilmLayer(args)
        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

        self.ft_model = ContentFiltering(args, ft_size)
        self.ft_comb = FeatureCombiner(args)

    def forward(self, x, time_x, ft_x, ft_n):
        time_x = self.time_nn(time_x)
        time_x = time_x * (x > 0)
        h = self.film_time(x, time_x)
        hf = self.ft_model(ft_x)
        h = self.ft_comb(h, hf, ft_n)
        h = self.dropout_input(h)
        h = self.sig_act(self.encoder(h))
        h = self.dropout_emb(h)
        p = self.decoder(h)
        if not self.training:
            p = self.limiter(p)
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.time_nn.get_reg_loss()
        reg_loss += self.ft_model.get_reg_loss()
        return reg_loss


class Autorec_DFT2(nn.Module):
    requires_time = True
    requires_fts = True
    requires_graph = False

    def __init__(self, args, input_size, ft_size, rating_range=(1, 5)):
        super(Autorec_DFT2, self).__init__()
        self.args = args

        self.time_nn = TimeNN(args, n_time_inputs=3)
        self.film_time = FilmLayer(args)
        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

        self.ft_model = ContentFiltering(args, ft_size)
        self.ft_comb = FeatureCombiner(args)

    def forward(self, x, time_x, ft_x, ft_n):
        time_x = self.time_nn(time_x)
        time_x = time_x * (x > 0)
        h = self.film_time(x, time_x)
        pf = self.ft_model(ft_x)
        h = self.dropout_input(h)
        h = self.sig_act(self.encoder(h))
        h = self.dropout_emb(h)
        p = self.decoder(h)
        p = self.ft_comb(p, pf, ft_n)
        if not self.training:
            p = self.limiter(p)
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.time_nn.get_reg_loss()
        reg_loss += self.ft_model.get_reg_loss()
        return reg_loss


class Autorec_DFGT(nn.Module):
    requires_time = True
    requires_fts = True
    requires_graph = True

    def __init__(self, args, input_size, ft_size, rating_range=(1, 5)):
        super(Autorec_DFGT, self).__init__()
        self.args = args

        self.time_nn = TimeNN(args, n_time_inputs=3)
        self.film_time = FilmLayer(args)
        self.dropout_input = nn.Dropout(0.7)
        self.encoder = nn.Linear(input_size, 500).to(args.device)
        self.sig_act = nn.Sigmoid()
        self.conv = GraphConv0D(args).to(args.device)
        self.dropout_emb = nn.Dropout(0.5)
        self.decoder = nn.Linear(500, input_size).to(args.device)
        self.limiter = nn.Hardtanh(rating_range[0], rating_range[1])

        self.ft_model = ContentFiltering(args, ft_size)
        self.ft_comb = FeatureCombiner(args)

    def forward(self, x, time_x, ft_x, ft_n, graph):
        graph = graph[0]
        time_x = self.time_nn(time_x)
        time_x = time_x * (x > 0)
        h = self.film_time(x, time_x)
        hf = self.ft_model(ft_x)
        h = self.ft_comb(h, hf, ft_n)
        h = self.dropout_input(h)
        h = self.sig_act(self.encoder(h))
        if graph['edge_index'].shape[0] == 2:
            h = self.conv(h, graph['edge_index'], graph['edge_weight'])
        h = self.dropout_emb(h)
        p = self.decoder(h)
        if not self.training:
            p = self.limiter(p)
        return p

    def get_reg_loss(self):
        reg_loss = self.args.reg / 2 * (
            torch.norm(self.encoder.weight) ** 2 +
            torch.norm(self.decoder.weight) ** 2
        )
        reg_loss += self.time_nn.get_reg_loss()
        reg_loss += self.ft_model.get_reg_loss()
        return reg_loss
