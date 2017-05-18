# -*- coding: utf-8 -*-
"""
Created on Sun May 14 19:49:51 2017

@author: Chin-Wei
"""

from BHNs import MLPWeightNorm_BHN
from ops import load_mnist
from utils import log_normal, log_laplace
import numpy as np

import lasagne
import theano
import theano.tensor as T
floatX = theano.config.floatX

# DK
from BHNs import HyperCNN
    
class MCdropoutCNN(object):
                     
    def __init__(self, dropout=None):
        weight_shapes = [(32,1,3,3),        # -> (None, 16, 14, 14)
                         (32,32,3,3),       # -> (None, 16,  7,  7)
                         (32,32,3,3)]       # -> (None, 16,  4,  4)
        n_kernels = np.array(weight_shapes)[:,1].sum()
        kernel_shape = weight_shapes[0][:1]+weight_shapes[0][2:]
        
        # needs to be consistent with weight_shapes
        args = [32,3,2,'same',lasagne.nonlinearities.rectify]#
        num_filters, filter_size, stride, pad, nonlinearity = args
        self.__dict__.update(locals())
        ##################
        
        layer = lasagne.layers.InputLayer([None,1,28,28])
        
        for j,ws in enumerate(self.weight_shapes):
            num_filters = ws[1]
            layer = lasagne.layers.Conv2DLayer(layer,
                num_filters, filter_size, stride, pad, nonlinearity
            )
            if dropout is not None and j!=len(self.weight_shapes)-1:
                if dropout == 'spatial':
                    layer = lasagne.layers.spatial_dropout(layer, dropout)
                else:
                    layer = lasagne.layers.dropout(layer, dropout)

        # MLP layers
        layer = lasagne.layers.DenseLayer(layer, 128)
        if dropout is not None and j!=len(self.weight_shapes)-1:
            layer = lasagne.layers.dropout(layer, dropout)
        layer = lasagne.layers.DenseLayer(layer, 10)

        layer.nonlinearity = lasagne.nonlinearities.softmax
        self.input_var = T.tensor4('input_var')
        self.target_var = T.matrix('target_var')
        self.learning_rate = T.scalar('leanring_rate')
        self.dataset_size = T.scalar('dataset_size') # useless
        
        self.layer = layer
        self.y = lasagne.layers.get_output(layer,self.input_var)
        self.y_det = lasagne.layers.get_output(layer,self.input_var,
                                               deterministic=True)
        
        losses = lasagne.objectives.categorical_crossentropy(self.y,
                                                             self.target_var)
        self.loss = losses.mean() + self.dataset_size * 0.
        self.params = lasagne.layers.get_all_params(self.layer)
        self.updates = lasagne.updates.adam(self.loss,self.params,
                                            self.learning_rate)

        print '\tgetting train_func'
        self.train_func = theano.function([self.input_var,
                                           self.target_var,
                                           self.dataset_size,
                                           self.learning_rate],
                                          self.loss,
                                          updates=self.updates)
        
        print '\tgetting useful_funcs'
        self.predict_proba = theano.function([self.input_var],self.y)
        self.predict = theano.function([self.input_var],self.y_det.argmax(1))
        




def train_model(train_func,predict_func,X,Y,Xt,Yt,
                lr0=0.1,lrdecay=1,bs=20,epochs=50):
    
    print 'trainset X.shape:{}, Y.shape:{}'.format(X.shape,Y.shape)
    N = X.shape[0]    
    records=list()
    
    t = 0
    for e in range(epochs):
        
        if lrdecay:
            lr = lr0 * 10**(-e/float(epochs-1))
        else:
            lr = lr0         
            
        for i in range(N/bs):
            x = X[i*bs:(i+1)*bs]
            y = Y[i*bs:(i+1)*bs]
            
            loss = train_func(x,y,N,lr)
            
            if t%100==0:
                print 'epoch: {} {}, loss:{}'.format(e,t,loss)
                tr_acc = (predict_func(X)==Y.argmax(1)).mean()
                te_acc = (predict_func(Xt)==Yt.argmax(1)).mean()
                print '\ttrain acc: {}'.format(tr_acc)
                print '\ttest acc: {}'.format(te_acc)
            t+=1
            
        records.append(loss)
        
    return records


def evaluate_model(predict_proba,X,Y,Xt,Yt,n_mc=1000):
    n = X.shape[0]
    MCt = np.zeros((n_mc,n,10))
    MCv = np.zeros((n_mc,n,10))
    for i in range(n_mc):
        MCt[i] = predict_proba(X)
        MCv[i] = predict_proba(Xt)
    
    Y_pred = MCt.mean(0).argmax(-1)
    Y_true = Y.argmax(-1)
    Yt_pred = MCv.mean(0).argmax(-1)
    Yt_true = Yt.argmax(-1)
    
    tr = np.equal(Y_pred,Y_true).mean()
    va = np.equal(Yt_pred,Yt_true).mean()
    print "train perf=", tr
    print "valid perf=", va

    ind_positive = np.arange(Xt.shape[0])[Yt_pred == Yt_true]
    ind_negative = np.arange(Xt.shape[0])[Yt_pred != Yt_true]
    
    ind = ind_negative[-1] #TO-DO: complete evaluation
    for ii in range(15): 
        print np.round(MCt[ii][ind] * 1000)
    
    ind = ind_negative[-2] #TO-DO: complete evaluation
    for ii in range(15): 
        print np.round(MCt[ii][ind] * 1000)

#def main():
if __name__ == '__main__':
    
    import argparse
    
    parser = argparse.ArgumentParser()
    
    # boolean: 1 -> True ; 0 -> False 
    parser.add_argument('--perdatapoint',default=0,type=int)
    parser.add_argument('--lrdecay',default=0,type=int)  
    
    parser.add_argument('--lr0',default=0.001,type=float)  
    parser.add_argument('--coupling',default=4,type=int) 
    parser.add_argument('--lbda',default=1,type=float)  
    parser.add_argument('--size',default=10000,type=int)      
    parser.add_argument('--bs',default=20,type=int)  
    parser.add_argument('--epochs',default=50,type=int)
    parser.add_argument('--prior',default='log_normal',type=str)
    parser.add_argument('--model',default='CNN',type=str)
    
    args = parser.parse_args()
    print args
    
    coupling = args.coupling
    perdatapoint = args.perdatapoint
    lrdecay = args.lrdecay
    lr0 = args.lr0
    lbda = np.cast['float32'](args.lbda)
    bs = args.bs
    epochs = args.epochs
    if args.prior=='log_normal':
        prior = log_normal
    elif args.prior=='log_laplace':
        prior = log_laplace
    else:
        raise Exception('no prior named `{}`'.format(args.prior))
    size = max(10,min(50000,args.size))
    
    filename = '/data/lisa/data/mnist.pkl.gz'
    train_x, train_y, valid_x, valid_y, test_x, test_y = load_mnist(filename)
    train_x = train_x.reshape((-1, 1, 28, 28))
    valid_x = valid_x.reshape((-1, 1, 28, 28))
    test_x = test_x.reshape((-1, 1, 28, 28))
    
    if args.model == 'hyperCNN':
        model = HyperCNN(lbda=lbda,
                         perdatapoint=perdatapoint,
                         prior=prior,
                         coupling=coupling)
    elif args.model == 'CNN':
        model = MCdropoutCNN()
    elif args.model == 'CNN_spatial_dropout':
        model = MCdropoutCNN(dropout='spatial')
    elif args.model == 'CNN_dropout':
        model = MCdropoutCNN(dropout=1)
    else:
        raise Exception('no model named `{}`'.format(args.model))
        
    recs = train_model(model.train_func,model.predict,
                       train_x[:size],train_y[:size],
                       valid_x,valid_y,
                       lr0,lrdecay,bs,epochs)
    
    evaluate_model(model.predict_proba,
                   train_x[:size],train_y[:size],
                   valid_x,valid_y)
    
    evaluate_model(model.predict_proba,
                   train_x[:size],train_y[:size],
                   test_x,test_y)


