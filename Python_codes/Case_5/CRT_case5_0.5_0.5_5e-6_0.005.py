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

import rfunctions as rf

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
radius0 = 200
radius2 = 500
b1 = 0.000005
b2 = 0.005 
Cin = 0.5
Cout = 0.5

# Q function
def Q(x,alpha, b1, b2, phi, n):
    return (n*torch.pi*np.sin(n*torch.pi*x))/(alpha*(((n*torch.pi)**2) + (phi**2)) - (b1+b2))

# g function
def g(phi,x):
    return 2*np.sinh(phi*x)

# function for calculating first term
def f1(x, phi, n, b1, alpha, t):
    return Q(x,alpha,b1,0,phi,n)*(np.exp(-b1*t) - np.exp(-alpha*t*(((n*torch.pi)**2) + phi**2)))


# function for calculating second term used in summation
def f2(x, phi, b2, alpha,t):
    return (g(phi,x)/g(phi,1)) - ((np.exp(-b2*t)*np.sin(np.sqrt((b2-alpha*phi*phi)/alpha)*x))/(np.sin(np.sqrt((b2-alpha*phi*phi)/alpha))))

def f3(x, phi, n , b2, alpha, t):
    return (2*b2*((-1)**n)*Q(x,alpha,0,b2,phi,n)*np.exp(-alpha*t*(((n*torch.pi)**2) + phi**2)))/(((n*torch.pi)**2) + phi**2)


# function for calculating concentration at given values of r,r0,r2,t
def conc(x, t):
    r0 = radius0 * 10 ** -9
    r2 = radius2 * 10 ** -9
    r = (r2-r0)*x + r0
    D = 10 ** -16  # diffusion coefficient
    c1 = Cin  # inner concentration-a
    c2 = Cout # outer concentration
    k = 10 ** -11
    a = D / ((r2 - r0) ** 2)  # alpha
    phi = np.sqrt(k / a)
    arr1 = []
    arr2 = []
    for n in range(1, 5000):
        arr1.append(f1(x, phi, n, b1, a, t))
    
    for n in range(1, 5000):
        arr2.append(f3(x, phi, n, b2, a, t))

    sf1 = sum(arr1)
    sf2 = sum(arr2)
    return ((2*c1*r0*a*sf1)/r) + ((c2*r2*(f2(x, phi, b2, a, t) - sf2))/r)


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
        r0 = radius0 * 10 ** -9
        r2 = radius2 * 10 ** -9
        k = 10 ** -11
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
        f = f_t - a * f_xx - (2 * D / (r0 * (r2 - r0) + g[:, 0:1] * (r2 - r0) * (r2 - r0)) - k) * f_x
        return self.loss_function(f, f_hat)

    def loss(self, x_BC, y_BC, x_PDE, f_hat, layers, w):
        loss_bc = self.lossBC(x_BC, y_BC, layers)
        loss_pde = self.lossPDE(x_PDE, f_hat, layers)
        return w * loss_bc + loss_pde

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
Nu_arr = [100]
Nf_arr = [1000]
Nr_arr = [400]
weights = [0.0001, 0.0002, 0.0003, 0.0004, 0.0005, 0.0007, 0.0008, 0.004, 0.007]
times = [1, 10, 25, 50, 100, 200, 300, 400]
count = 0
f = open('output.txt', 'a')
for Nr in Nr_arr:
    for Nf in Nf_arr:
        for Nu in Nu_arr:
            for w in weights:
                for tim in times:

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
                    bottom_X = torch.hstack((X[0, :][:, None], T[0, :][:,
                                                               None]))  # First row # The [:,None] is to give it the right dimension
                    c1 = Cin*(np.exp(-b1*t))
                    bottom_Y = c1 * torch.ones(bottom_X.shape[0], 1)
                    # Top Edge: x=max; 0=<t=<1
                    c2 = Cout*(1 - np.exp(-b2*t))
                    top_X = torch.hstack(
                        (X[-1, :][:, None],
                         T[-1, :][:, None]))  # Last row # The [:,None] is to give it the right dimension
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
                    X_train_Nf = torch.vstack(
                        (X_train_Nf, X_train_Nu))  # Add the training poinst to the collocation points
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
                    f.write("total_points_x : " + str(total_points_x) + '\n')
                    print("total_points_t : " + str(total_points_t))
                    f.write("total_points_t : " + str(total_points_t) + '\n')
                    print("Nu : " + str(Nu))
                    f.write("Nu : " + str(Nu) + '\n')
                    print("Nf : " + str(Nf))
                    print("lambda:" + str(w))
                    print("time:" + str(tim))
                    f.write("Nf : " + str(Nf) + '\n')
                    f.write("lambda:" + str(w) + '\n')
                    f.write("time:" + str(tim) + '\n')
                    for j in range(5):
                        a_rel = 0
                        a_train = 0
                        a_test = 0
                        v = 10
                        print('iteration no.:', j + 1)
                        f.write('iteration no.:' + str(j + 1))
                        f.write('\n')
                        ## start
                        for i in range(steps):
                            if i == 0:
                                print("Training Loss-----Test Loss")
                                f.write("Training Loss-----Test Loss" + '\n')
                            loss = PINN.loss(X_train_Nu, Y_train_Nu, X_train_Nf, f_hat, layers,
                                             w)  # use mean squared error
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
                                f.write(str(tre) + '---' + str(te))
                                f.write('\n')
                        print("Average losses:")
                        f.write("Average losses:" + '\n')
                        print(round(a_train / v, 15), '---', round(a_test / v, 9))
                        f.write(str(round(a_train / v, 15)) + '---' + str(round(a_test / v, 9)))
                        f.write('\n')
                        ## end
                        y1_all = PINN(X_test)
                        x1_all = X_test[:, 0]
                        # t1 = torch.ones(X_test[:, 1].size())
                        t1_all = X_test[:, 1]

                        a, b = rf.get_idx(t1_all, tim)
                        x1 = x1_all[a:b + 1]
                        y1 = y1_all[a:b + 1]
                        t1 = t1_all[a:b + 1]
                        # arr_x1 = x1.reshape(shape=[total_points_x, total_points_t]).transpose(1, 0).detach().cpu()
                        # arr_T1 = t1.reshape(shape=[total_points_x, total_points_t]).transpose(1, 0).detach().cpu()
                        # arr_y1 = y1.reshape(shape=[total_points_x, total_points_t]).transpose(1, 0).detach().cpu()
                        # arr_y_test = y_test.reshape(shape=[total_points_x, total_points_t]).transpose(1, 0).detach().cpu()
                        arr_x1 = x1.detach().numpy()
                        arr_y1 = y1.detach().numpy()
                        arr_y_test = y_test[a:b + 1].detach().numpy()

                        xtst = np.arange(x_min+0.0005, x_max, 0.0005)
                        plt.figure()
                        plt.title("predicted c(r,t) function for lambda=" + str(w) + ", iteration: " + str(
                            j + 1) + ", time:" + str(tim))
                        plt.xlabel("x(normalised r)")
                        plt.ylabel("concentration")
                        plt.plot(xtst, conc(xtst, tim), label="analytical function")
                        plt.plot(arr_x1, arr_y1, label="predicted function", linestyle='dashed')
                        plt.ylim(-0.1, 1.1)
                        # print(arr_x1)
                        # print(arr_y1)
                        p_arr_x1 = [arr_x1]
                        p_arr_y1 = arr_y1.T
                        a_arr_x1 = [xtst]
                        a_arr_y1 = [conc(xtst, tim)]
                        data = np.concatenate((p_arr_x1, p_arr_y1), axis=0)
                        #data_analytical = np.concatenate((a_arr_x1, a_arr_y1), axis =0)
                        dataset = data.T
                        #dataset_analytical =data_analytical.T
                        np.savetxt(
                            "Case5_" + str(Cin) + "_" + str(Cout) + "_" + str(b1) + "_" + str(b2) + "_" + str(radius0) + "_" + str(radius2) + "_" + str(w) + '_' + str(j + 1) + '_' + str(
                                tim) + ".csv", dataset, delimiter=",")
                        #np.savetxt("data_analytical_"+str(radius0)+"_"+str(radius2)+"_"+str(w)+'_'+str(j+1)+'_'+str(tim)+".csv" , dataset_analytical, delimiter = ",")
                        # plt.plot(arr_x1, arr_y_test,label="on test set")
                        plt.legend()
                        plt.savefig(
                            'Case5_' + str(Cin) + "_" + str(Cout) + "_" + str(b1) + "_" + str(b2)+ "_" + str(radius0) + "_" + str(radius2) + '_' + str(w) + '_' + str(j + 1) + '_' + str(
                                tim) + '.png')

    #     Nu= Nu+100
    #   Nf=Nf+1000
    # Nr=Nr+100
