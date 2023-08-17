import sys, os
import torch
import random

import torch as th
import torch.nn as nn
import torch.nn.functional as F
from utils import *
from dgl.nn.pytorch import GraphConv as GraphConv
from dgl.nn.pytorch import GATConv as GATConv
from dgl.nn import GINConv as GINConv

from torch.autograd import Variable
from torch.nn import init
import time
import csv

import numpy as np
from scipy.stats import multivariate_normal
from torch.nn.functional import normalize


global haveedge
haveedge = False

class node_mlp(torch.nn.Module):
    """
    This layer apply a chain of mlp on each node of tthe graph.
    thr input is a matric matrrix with n rows whixh n is the nide number.
    """

    def __init__(self, input, layers=[16, 16], normalize=False, dropout_rate=0):
        """
        :param input: the feture size of input matrix; Number of the columns
        :param normalize: either use the normalizer layer or not
        :param layers: a list which shows the ouyput feature size of each layer; Note the number of layer is len(layers)
        """
        super().__init__()
        # super(node_mlp, self).__init__()
        self.layers = torch.nn.ModuleList([torch.nn.Linear(input, layers[0])])

        for i in range(len(layers) - 1):
            self.layers.append(torch.nn.Linear(layers[i], layers[i + 1]))

        self.norm_layers = None
        if normalize:
            self.norm_layers = torch.nn.ModuleList([torch.nn.BatchNorm1d(c) for c in [input] + layers])
        self.dropout = torch.nn.Dropout(dropout_rate)
        # self.reset_parameters()

    def forward(self, in_tensor, activation=torch.tanh):
        h = in_tensor
        for i in range(len(self.layers)):
            if self.norm_layers != None:
                if len(h.shape) == 2:
                    h = self.norm_layers[i](h)
                else:
                    shape = h.shape
                    h = h.reshape(-1, h.shape[-1])
                    h = self.norm_layers[i](h)
                    h = h.reshape(shape)
            h = self.dropout(h)
            h = self.layers[i](h)
            h = activation(h)
        return h





class multi_layer_GCN(torch.nn.Module):
    def __init__(self, in_feature, latent_dim=32, layers=[64]):
        """
        :param in_feature: the size of input feature; X.shape()[1]
        :param latent_dim: the dimention of each embedded node; |z| or len(z)
        :param layers: a list in which each element determine the size of corresponding GCNN Layer.
        """
        super(multi_layer_GCN, self).__init__()
        layers = [in_feature] + layers
        if len(layers) < 1: raise Exception("sorry, you need at least two layer")
        self.ConvLayers = torch.nn.ModuleList(
            GraphConv(layers[i], layers[i + 1], activation=None, bias=False, weight=True) for i in
            range(len(layers) - 1))

        self.q_z_mean = GraphConv(layers[-1], latent_dim, activation=None, bias=False, weight=True)

        self.q_z_std = GraphConv(layers[-1], latent_dim, activation=None, bias=False, weight=True)

    def forward(self, adj, x):
        dropout = torch.nn.Dropout(0)
        for conv_layer in self.ConvLayers:
            x = torch.tanh(conv_layer(adj, x))
            x = dropout(x)

        m_q_z = self.q_z_mean(adj, x)
        std_q_z = torch.relu(self.q_z_std(adj, x)) + .0001

        z = self.reparameterize(m_q_z, std_q_z)
        return z, m_q_z, std_q_z,

    def reparameterize(self, mean, std):
        eps = torch.randn_like(std)
        return eps.mul(std).add(mean)





class multi_layer_GIN(torch.nn.Module):
    def __init__(self, in_feature, latent_dim=32, layers=[64]):
        """
        :param in_feature: the size of input feature; X.shape()[1]
        :param latent_dim: the dimention of each embedded node; |z| or len(z)
        :param layers: a list in which each element determine the size of corresponding GCNN Layer.
        """
        super(multi_layer_GIN, self).__init__()
        layers = [in_feature] + layers
        if len(layers) < 1: raise Exception("sorry, you need at least two layer")
        self.ConvLayers = torch.nn.ModuleList(
            GINConv(th.nn.Linear(in_feature, latent_dim), 'max') for i in
            range(len(layers) - 1))

        self.q_z_mean = GINConv(th.nn.Linear(in_feature, latent_dim), 'max')

        self.q_z_std = GINConv(th.nn.Linear(in_feature, latent_dim), 'max')

    def forward(self, adj, x):
        dropout = torch.nn.Dropout(0)
        for conv_layer in self.ConvLayers:
            x = torch.tanh(conv_layer(adj, x))
            x = dropout(x)

        m_q_z = self.q_z_mean(adj, x)
        std_q_z = torch.relu(self.q_z_std(adj, x)) + .0001

        z = self.reparameterize(m_q_z, std_q_z)
        return z, m_q_z, std_q_z,

    def reparameterize(self, mean, std):
        eps = torch.randn_like(std)
        return eps.mul(std).add(mean)



class multi_layer_GAT(torch.nn.Module):
    def __init__(self, in_feature, latent_dim=32, layers=[64]):
        """
        :param in_feature: the size of input feature; X.shape()[1]
        :param latent_dim: the dimention of each embedded node; |z| or len(z)
        :param layers: a list in which each element determine the size of corresponding GCNN Layer.
        """
        super(multi_layer_GAT, self).__init__()
        layers = [in_feature] + layers
        self.num_head = 8
        latent_dim =int(latent_dim/(8**2))
        
        if len(layers) < 1: raise Exception("sorry, you need at least two layer")
        self.ConvLayers = torch.nn.ModuleList(
            GATConv(layers[i], layers[i + 1], activation=None, bias=False, num_heads=self.num_head) for i in
            range(len(layers) - 1))

        self.q_z_mean = GATConv(layers[-1], latent_dim, activation=None, bias=False, num_heads=self.num_head)

        self.q_z_std = GATConv(layers[-1], latent_dim, activation=None, bias=False, num_heads=self.num_head )

    def forward(self, adj, x):
        dropout = torch.nn.Dropout(0)
        for conv_layer in self.ConvLayers:
            x = torch.tanh(conv_layer(adj, x))
            x = dropout(x)

        m_q_z = self.q_z_mean(adj, x)
        std_q_z = torch.relu(self.q_z_std(adj, x)) + .0001
        
        m_q_z_flatten = torch.flatten(m_q_z, start_dim=1)
        std_q_z_flatten = torch.flatten(std_q_z, start_dim=1)
 

        z = self.reparameterize(m_q_z_flatten, std_q_z_flatten)
        return z, m_q_z_flatten, std_q_z_flatten

    def reparameterize(self, mean, std):
        eps = torch.randn_like(std)
        return eps.mul(std).add(mean)






class MultiLatetnt_SBM_decoder(torch.nn.Module):

    def __init__(self, number_of_rel, Lambda_dim, in_dim, normalize, DropOut_rate, node_trns_layers=[32]):
        super(MultiLatetnt_SBM_decoder, self).__init__()

        self.nodeTransformer = torch.nn.ModuleList(
            node_mlp(in_dim, node_trns_layers + [Lambda_dim], normalize, DropOut_rate) for i in range(number_of_rel))

        self.lambdas = torch.nn.ParameterList(
            torch.nn.Parameter(torch.Tensor(Lambda_dim, Lambda_dim)) for i in range(number_of_rel))
        self.numb_of_rel = number_of_rel
        self.reset_parameters()

    def reset_parameters(self):
        for i, weight in enumerate(self.lambdas):
            self.lambdas[i] = init.xavier_uniform_(weight)

    def forward(self, in_tensor):
        gen_adj = []
        for i in range(self.numb_of_rel):
            z = self.nodeTransformer[i](in_tensor)
            h = torch.mm(z, (torch.mm(self.lambdas[i], z.t())))
            gen_adj.append(h)
        return torch.sum(torch.stack(gen_adj), 0)



class VGAE_FrameWork(torch.nn.Module):
    def __init__(self, latent_dim, encoder, decoder, feature_encoder, mlp_decoder=False, layesrs=None):
        """
        :param latent_dim: the dimention of each embedded node; |z| or len(z)
        :param decoder:
        :param encoder:
        :param mlp_decoder: either apply an multi layer perceptorn on each decoeded embedings
        """
        super(VGAE_FrameWork, self).__init__()
        self.decoder = decoder
        self.encoder = encoder
        self.leakyRelu = nn.LeakyReLU()
        self.latent_dim = latent_dim
        self.feature_encoder = feature_encoder
        self.mq = None
        self.sq = None

        if mlp_decoder:
            self.embedding_level_mlp = node_mlp(input=latent_dim, layers=layesrs)

        self.dropout = torch.nn.Dropout(0)
        self.reset_parameters()

    def forward(self, adj, x, target_edges, sampling_method, is_prior, train=True):
        z_0 = self.get_z(x, self.latent_dim)  # attribute encoder
        z, m_z, std_z = self.inference(adj, z_0)  # link encoder
        generated_adj = self.generator(z)  # link decoder
            
        if not train:
            z_0 = self.get_z(x, self.latent_dim)  # attribute encoder
            z, m_z, std_z = self.inference(adj, z_0)  # link encoder

            generated_adj = self.generator(z)  # link decoder

            if is_prior:
                
                if sampling_method == "normalized":

                    A0 = self.run_monte(generated_adj, x, adj, target_edges)
                    A1 = self.run_importance_sampling(generated_adj, x, adj, target_edges)
                    
                    # get softmax and return
                    generated_adj = torch.exp(A1) / (torch.exp(A0) + torch.exp(A1))


                elif sampling_method=='monte':
                    generated_adj = self.run_monte(generated_adj, x, adj, target_edges)
                    
                elif sampling_method == 'importance_sampling':
                    generated_adj = self.run_importance_sampling(generated_adj, x, adj, target_edges)
                    
                else: 
                    # deterministic
                    generated_adj = self.generator(m_z) # Give the mean

            else:
                self.mq = m_z
                self.sq = std_z

        return std_z, m_z, z, generated_adj

    def run_monte(self, generated_adj, x, adj, targets):
        
        # make edge list from the ends of the target nodes
        targets = np.array(targets)
        target_node = np.array([targets[-1]] * targets.shape[0]) 
        target_edges = np.stack((targets, target_node), axis=1)[:-1]
        
        s = generated_adj
        num_it = 30
        for i in range(num_it - 1):
            z_0 = self.get_z(x, self.latent_dim)  # attribute encoder
            z, m_z, std_z = self.inference(adj, z_0)
            generated_adj = self.generator(z)
            s += generated_adj
            
        generated_adj = s / num_it

        return generated_adj

    def run_importance_sampling(self, generated_adj, x, adj, targets):

        targets = np.array(targets)
        target_node = np.array([targets[-1]] * targets.shape[0]) 
        target_edges = np.stack((targets, target_node), axis=1)[:-1]
        
        s = generated_adj
        num_it = 30
        for i in range(num_it - 1):

            z_s = self.reparameterize(self.mq, self.sq)

            # get z from prior
            z_0 = self.get_z(x, self.latent_dim)  # attribute encoder
            z, m_z, std_z = self.inference(adj, z_0)  # link encoder


            prior_pdf, recog_pdf = get_pdf(m_z, std_z, self.mq, self.sq, z_s, targets)

            coefficient = torch.tensor(prior_pdf - recog_pdf)


            generated_adj = self.generator(z_s)

            log_generated_adj = torch.log(torch.sigmoid(generated_adj))

            log_generated_adj_added = torch.add(log_generated_adj, coefficient)

            generated_adj_final = torch.exp(log_generated_adj_added)

            s += generated_adj_final
            
        generated_adj = s / num_it
        return generated_adj


    def reset_parameters(self):
        pass

    def reparameterize(self, mean, std):
        eps = torch.randn_like(std)
        return eps.mul(std).add(mean)

    # inference model
    def inference(self, adj, x):
        x = F.normalize(x,p=2,dim=1) * 1.8
        if (haveedge):
            z, m_q_z, std_q_z, edge_emb = self.encoder(adj, x)
            return z, m_q_z, std_q_z, edge_emb
        else:
            z, m_q_z, std_q_z = self.encoder(adj, x)
            return z, m_q_z, std_q_z


    def generator_edge(self, z, edge_emb):

        gen_adj = []
        if (haveedge):
            adj = self.decoder(z, edge_emb)
        else:
            adj = self.decoder(z)
        return adj

    def generator(self, z):

        gen_adj = []
        adj = self.decoder(z)
        return adj

    def get_z(self, x, latent_dim):
        """Encode a batch of data points, x, into their z representations."""

        return self.feature_encoder(x)


class feature_encoder(torch.nn.Module):
    def __init__(self, in_feature, latent_dim=128):
        """
        :param in_feature: the size of input feature; X.shape()[1]
        :param latent_dim: the dimention of each embedded node; |z| or len(z)
        :param layers: a list in which each element determine the size of corresponding GCNN Layer.
        """
        super(feature_encoder, self).__init__()
        self.leakyRelu = nn.LeakyReLU()

        self.std = nn.Linear(in_features=in_feature.shape[1], out_features=latent_dim)
        self.mean = nn.Linear(in_features=in_feature.shape[1], out_features=latent_dim)


    def forward(self, x):
        x = normalize(x, p=1.0, dim = 1)
        m_q_z = self.mean(x)
        std_q_z = torch.relu(self.std(x)) + .0001

        z = self.reparameterize(m_q_z, std_q_z)
        return z

    def reparameterize(self, mean, std):
        eps = torch.randn_like(std)
        return eps.mul(std).add(mean)