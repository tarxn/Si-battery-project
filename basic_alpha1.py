# -*- coding: utf-8 -*-
"""basic_alpha.py

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1OVPrpKWy_hcdDL3DjsHCmQcEI8KAXbHc
"""

# ! pip install pyDOE
import torch
import torch.autograd as autograd  # computation graph
from torch import Tensor  # tensor node in the computation graph
import torch.nn as nn  # neural networks
import torch.optim as optim  # optimizers e.g. gradient descent, ADAM, etc.
# import tensorflow as tf
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from mpl_toolkits.axes_grid1 import make_axes_locatable
from mpl_toolkits.mplot3d import Axes3D
import matplotlib.ticker
# from sklearn.model_selection import train_test_split
# from google.colab import files

import numpy as np
import time
from pyDOE import lhs  # Latin Hypercube Sampling
# import scipy.io
from scipy import stats
import math

# Set default dtype to float32
torch.set_default_dtype(torch.float)

# PyTorch random number generator
torch.manual_seed(1234)

# Random number generators in other libraries
np.random.seed(1234)

# Device configuration
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

print(device)

if device == 'cuda':
    print(torch.cuda.get_device_name())

steps = 20000
lr = 1e-3
layers = np.array([2, 32, 32, 1])  # hidden layers
# To generate new data:
x_min = 0
x_max = 1
t_min = 0
t_max = 400


# function for calculating first term
def f1(x, r0, r2, c1, c2):
    return ((r0 * c1) / (r0 + x * (r2 - r0))) + ((r2 * c2 - r0 * c1) * x) / (r0 + x * (r2 - r0))


# function for calculating second term used in summation
def f2(x, r0, r2, c1, c2, n, a, t):
    return ((2 / ((r0 + x * (r2 - r0)) * torch.pi)) * ((r2 * c2 * ((-1) ** n)) - r0 * c1) * (
        np.exp(-((n ** 2) * (torch.pi ** 2) * a * t))) * np.sin(n * torch.pi * x)) / n


# function for calculating concentration at given values of r,r0,r2,t
def conc(x, t):
    r0 = 200 * 10 ** -9
    r2 = 500 * 10 ** -9
    D = 10 ** -16  # diffusion coefficient
    c1 = 0  # inner concentration
    c2 = 1  # outer concentration
    a = D / ((r2 - r0) ** 2)  # alpha
    arr = []
    for n in range(1, 50):
        arr.append(f2(x, r0, r2, c1, c2, n, a, t))

    sf = sum(arr)
    return f1(x, r0, r2, c1, c2) + sf


def plot3D_Matrix(x, t, y):
    X, T = x, t
    F_xt = y
    fig, ax = plt.subplots(1, 1)
    cp = ax.contourf(T, X, F_xt, 20, cmap="rainbow")
    fig.colorbar(cp)  # Add a colorbar to a plot
    ax.set_title('C(x,t)')
    ax.set_xlabel('t')
    ax.set_ylabel('x')
    plt.show()
    ax = plt.axes(projection='3d')
    ax.plot_surface(T.numpy(), X.numpy(), F_xt.numpy(), cmap="rainbow")
    ax.set_xlabel('t')
    ax.set_ylabel('x')
    ax.set_zlabel('C(x,t)')
    plt.show()
    # X, T = x, t[0]
    # F_xt = y


# w = 0.1

class FCN(nn.Module):
    ##Neural Network
    def __init__(self, layers):
        super().__init__()  # call __init__ from parent class
        'activation function'
        self.activation = nn.Tanh()
        self.layers = layers
        'loss function'
        self.loss_function = nn.MSELoss(reduction='mean')
        'Initialise neural network as a list using nn.Modulelist'
        self.linears = nn.ModuleList([nn.Linear(layers[i], layers[i + 1]) for i in range(len(layers) - 1)])
        self.iter = 0  # For the Optimizer
        'Xavier Normal Initialization'
        for i in range(len(layers) - 1):
            nn.init.xavier_normal_(self.linears[i].weight.data, gain=1.0)
            # set biases to zero
            nn.init.zeros_(self.linears[i].bias.data)

    'foward pass'

    def forward(self, x):
        if torch.is_tensor(x) != True:
            x = torch.from_numpy(x)
        a = x.float()
        for i in range(len(layers) - 2):
            z = self.linears[i](a)
            a = self.activation(z)
        a = self.linears[-1](a)
        return a

    'Loss Functions'

    # Loss BC
    def lossBC(self, x_BC, y_BC, layers):
        loss_BC = self.loss_function(self.forward(x_BC), y_BC)
        return loss_BC

    # Loss PDE
    def lossPDE(self, x_PDE, f_hat, layers):
        r0 = 200 * 10 ** -9
        r2 = 500 * 10 ** -9
        D = 10 ** -16
        a = D / ((r2 - r0) ** 2)
        g = x_PDE.clone()
        g.requires_grad = True  # Enable differentiation
        f = self.forward(g)
        f_x_t = autograd.grad(f, g, torch.ones([g.shape[0], 1]).to(device), retain_graph=True, create_graph=True)[
            0]  # first derivative
        f_xx_tt = autograd.grad(f_x_t, g, torch.ones(g.shape).to(device), create_graph=True)[0]  # second derivative
        f_t = f_x_t[:, [1]]  # we select the 2nd element for t (the first one is x) (Remember the input X=[x,t])
        f_x = f_x_t[:, [0]]
        f_xx = f_xx_tt[:, [0]]  # we select the 1st element for x (the second one is t) (Remember the input X=[x,t])
        f = f_t - a * f_xx - (2 * D / (r0 * (r2 - r0) + g[:, 0:1] * (r2 - r0) * (r2 - r0))) * f_x
        return self.loss_function(f, f_hat)

    def loss(self, x_BC, y_BC, x_PDE, f_hat, layers):
        loss_bc = self.lossBC(x_BC, y_BC, layers)
        loss_pde = self.lossPDE(x_PDE, f_hat, layers)
        return loss_bc + w * loss_pde

    def rel_loss(self, x_BC, y_BC, x_PDE, f_hat, layers):
        loss_bc = self.lossBC(x_BC, y_BC, layers)
        loss_pde = self.lossPDE(x_PDE, f_hat, layers)
        return torch.sqrt(loss_bc / loss_pde)

    # Optimizer              X_train_Nu,Y_train_Nu,X_train_Nf
    def closure(self, f_hat, layers):
        optimizer.zero_grad()
        loss = self.loss(X_train_Nu, Y_train_Nu, X_train_Nf, f_hat, layers)
        loss.backward()
        self.iter += 1
        if self.iter % 100 == 0:
            loss2 = self.lossBC(X_test, Y_test)
            print("Training Error:", loss.detach().cpu().numpy(), "---Testing Error:", loss2.detach().cpu().numpy())
        return loss


"""## **Parameter array**"""

# Nu: Number of training points # Nf: Number of collocation points (Evaluate PDE)
Nu_arr = [1000, 2000]
Nf_arr = [10000, 20000]
Nr_arr = [1000, 2000]
# w=[0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1]
w = 0.1
count = 0
for Nr in Nr_arr:
    for Nf in Nf_arr:
        for Nu in Nu_arr:
            for i_ in range(10):
                x1 = np.arange(x_min, x_max, 0.005)
                plt.plot(x1, conc(x1, 50), label="analytical function")

                count += 1
                print('----------------------------- case:', count, '----------------------------')
                total_points_x = Nr
                total_points_t = Nr
                x = torch.linspace(x_min, x_max, total_points_x).view(-1, 1)
                t = torch.linspace(t_min, t_max, total_points_t).view(-1, 1)
                X, T = torch.meshgrid(x.squeeze(1), t.squeeze(1))
                # Evaluate real function
                y_real = conc(X, T)
                x_test = torch.hstack((X.transpose(1, 0).flatten()[:, None], T.transpose(1, 0).flatten()[:, None]))
                y_test = y_real.transpose(1, 0).flatten()[:, None]  # Colum major Flatten (so we transpose it)
                # Domain bounds
                lb = x_test[0]  # first value
                ub = x_test[-1]  # last value
                left_X = torch.hstack((X[:, 0][:, None], T[:, 0][:,
                                                         None]))  # First column # The [:,None] is to give it the right dimension
                left_Y = torch.zeros(left_X.shape[0], 1)
                # Boundary Conditions
                # Bottom Edge: x=min; tmin=<t=<max
                bottom_X = torch.hstack(
                    (X[0, :][:, None], T[0, :][:, None]))  # First row # The [:,None] is to give it the right dimension
                bottom_Y = torch.zeros(bottom_X.shape[0], 1)
                # Top Edge: x=max; 0=<t=<1
                c2 = 1
                top_X = torch.hstack(
                    (X[-1, :][:, None], T[-1, :][:, None]))  # Last row # The [:,None] is to give it the right dimension
                top_Y = c2 * torch.ones(top_X.shape[0], 1)
                # Get all the training data into the same dataset
                X_train = torch.vstack([left_X, bottom_X, top_X])
                Y_train = torch.vstack([left_Y, bottom_Y, top_Y])
                # Choose(Nu) points of our available training data:
                idx = np.random.choice(X_train.shape[0], Nu, replace=False)
                X_train_Nu = X_train[idx, :]
                Y_train_Nu = Y_train[idx, :]
                # Collocation Points (Evaluate our PDe)
                # Choose(Nf) points(Latin hypercube)
                X_train_Nf = lb + (ub - lb) * lhs(2, Nf)  # 2 as the inputs are x and t
                # sample = X_train_Nf.random(n=Nf)
                X_train_Nf = torch.vstack((X_train_Nf, X_train_Nu))  # Add the training poinst to the collocation points
                torch.manual_seed(123)
                # Store tensors to GPU
                X_train_Nu = X_train_Nu.float().to(device)  # Training Points (BC)
                Y_train_Nu = Y_train_Nu.float().to(device)  # Training Points (BC)
                X_train_Nf = X_train_Nf.float().to(device)  # Collocation Points
                f_hat = torch.zeros(X_train_Nf.shape[0], 1).to(device)  # to minimize function

                X_test = x_test.float().to(device)  # the input dataset (complete)
                Y_test = y_test.float().to(device)  # the real solution

                # Create Model
                PINN = FCN(layers)
                PINN.to(device)
                # print(PINN)
                params = list(PINN.parameters())
                optimizer = torch.optim.Adam(PINN.parameters(), lr=lr, amsgrad=False)
                '''
                'L-BFGS Optimizer'
                optimizer = torch.optim.LBFGS(PINN.parameters(), lr=lr, 
                                              max_iter = steps, 
                                              max_eval = None, 
                                              tolerance_grad = 1e-05, 
                                              tolerance_change = 1e-09, 
                                              history_size = 100, 
                                              line_search_fn = 'strong_wolfe')'''
                start_time = time.time()

                print("total_points_x : " + str(total_points_x))
                print("total_points_t : " + str(total_points_t))
                print("Nu : " + str(Nu))
                print("Nf : " + str(Nf))
                print("lambda:" + str(w))

                # print(y1_arr)
                for j in range(3):
                    a_rel = 0
                    a_train = 0
                    a_test = 0
                    v = 10
                    print('iteration no.:', j + 1)
                    for i in range(steps):
                        if i == 0:
                            print("Training Loss-----Test Loss")
                        loss = PINN.loss(X_train_Nu, Y_train_Nu, X_train_Nf, f_hat, layers)  # use mean squared error
                        # rel_er = PINN.rel_loss(X_train_Nu, Y_train_Nu, X_train_Nf, f_hat, layers)  # .
                        optimizer.zero_grad()
                        loss.backward()
                        # rel_er.backward()
                        optimizer.step()
                        if i % (steps / v) == 0:
                            with torch.no_grad():
                                test_loss = PINN.lossBC(X_test, Y_test, layers)

                            # re = rel_er.detach().cpu().numpy()  # rel. error
                            tre = loss.detach().cpu().numpy()  # training error
                            te = test_loss.detach().cpu().numpy()  # test error

                            # a_rel = a_rel + re
                            a_train = a_train + tre
                            a_test = a_test + te

                            print(tre, '---', te)
                    print("Average losses:")
                    print(round(a_train / v, 15), '---', round(a_test / v, 9))
                    y1_all = PINN(X_test)
                    x1_all = X_test[:, 0]
                    # t1 = torch.ones(X_test[:, 1].size())
                    t1_all=X_test[:, 1]

                    x1=x1_all
                    y1=y1_all
                    t1=t1_all
                    print(x1_all)
                    print(t1_all)
                    print(y1_all)

                    arr_x1 = x1.reshape(shape=[total_points_x, total_points_t]).transpose(1, 0).detach().cpu()
                    arr_T1 = t1.reshape(shape=[total_points_x, total_points_t]).transpose(1, 0).detach().cpu()
                    arr_y1 = y1.reshape(shape=[total_points_x, total_points_t]).transpose(1, 0).detach().cpu()
                    arr_y_test = y_test.reshape(shape=[total_points_x, total_points_t]).transpose(1, 0).detach().cpu()
                    # plot3D_Matrix(arr_x1,arr_T1,arr_y1,j+1)
                    # x = torch.linspace(x_min, x_max, total_points_x).view(-1, 1)
                    # t = torch.linspace(t_min, t_max, total_points_t).view(-1, 1)

                    # plot3D_Matrix(arr_x1, arr_T1, arr_y1)

                    plt.title("predicted c(r,t) function for lambda=" + str(w))
                    plt.xlabel("x(normalised r)")
                    plt.ylabel("concentration")
                    plt.plot(arr_x1, arr_y1)
                    plt.legend()
                    plt.show()

                w = w + 0.1

    #     Nu= Nu+100
    #   Nf=Nf+1000
    # Nr=Nr+100

