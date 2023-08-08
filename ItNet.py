'''ItNet Script'''

 #Lambda starts as 1

#Then as itnet trained, UNet refined and lambda varied

#lambde - check LPD initialisation func shows how lambda changed


import os
import random
import numpy as np
import fnmatch
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torchvision
import tomosipo as ts
from ts_algorithms import fdk
import AItomotools.CTtools.ct_utils as ct
from torch.nn import BCEWithLogitsLoss
from torch.optim import Adam
from torch.utils.data import DataLoader
from torchvision import transforms
from tqdm import tqdm
import time

from UNet import UNet
from ItNetDataLoader import loadData
import config

#img = fdk(A, sinoNoisy)
    
class ItNet(nn.Module):
    def __init__(self, noIter=config.ITNET_ITS, lmda=[1.1183, 1.3568, 1.4271, 0.0808], lmdaLearnt=True, resnetFac=1):
        super(ItNet, self).__init__()

        #self.unet = unet #should be in nn.ModuleList()
        self.dev = torch.device("cuda:3")

        self.unet = []
        for i in range(noIter):                                    # number of iterations
            unetTmp = UNet().to(self.dev)
            stateDict = torch.load("/local/scratch/public/obc22/trainCheckpts/epoch119.pt")['model_state_dict']
            unetTmp.load_state_dict(stateDict)
            self.unet.append(unetTmp)

        self.unet = nn.ModuleList(self.unet)
        self.noIter = noIter
        lmdaLearnt = [lmdaLearnt] * len(lmda)
        self.lmda = nn.ParameterList(
            [nn.Parameter(torch.tensor(lmda[i]), 
            requires_grad=lmdaLearnt[i]) for i in range(len(lmda))])
        self.resnetFac =resnetFac
        
        vg = ts.volume(shape=(1, *(512,512)), size=(300/512, 300, 300))
        # Define acquisition geometry. We want fan beam, so lets make a "cone" beam and make it 2D. We also need sod and sdd, so we set them up to something medically reasonable.
        pg = ts.cone(
            angles=360, shape=(1, 900), size=(1, 900), src_orig_dist=575, src_det_dist=1050
        )
        # A is now an operator.
        self.A = ts.operator(vg, pg)
    
    def forward2(self, sino):

        #print("ITNET")
        #print(sino)
        #print(A)
        sino =sino.to(self.dev)
        img = torch.empty(0,512,512).to(self.dev)
        for i in sino:
            i = i.to(self.dev)
            img = torch.cat((img, fdk(self.A, i)), 0)
        #L,D,H,W = img.shape
        img = torch.unsqueeze(img, 1)
        #s = torch.zeros(L,D,H,W)

        for i in range(self.noIter):
            self.unet[i].train()
            #with torch.no_grad():
            img = self.unet[i](img)
            #img = img - self.lmda[i] * fdk(A, self.getSino(img) - sino)
            img2 = torch.zeros_like(img)
            for j in range(img.shape[0]):
                diff = (self.getSino(img[j])-sino[j]).to(self.dev)
                img2[j]=fdk(self.A, diff)
            #img2 = img - self.lmda[i]*img2 #v4
            img = img - self.lmda[i]*img2 #v3
            #img2 = img - self.lmda[i]*img #v1
            

        return img
    
    def forward(self, sino):

        B, C, W, H = sino.shape
        img = sino.new_zeros(B, 1, *[1,512,512][1:])
        update = sino.new_zeros(B, 1, *[1,512,512][1:])
        # Start from FDK
        for i in range(sino.shape[0]):
            img[i] = fdk(self.A, sino[i])

        for i in range(self.noIter):#range(self.model_parameters.n_iters):
            unet = self.unet[i]
            img = unet(img)

            for j in range(img.shape[0]):
                update[j] = self.lmda[i] * fdk(self.A, self.getSino(img[j]) - sino[j])
                #update[j] = self.lmda[i] * self.A.T(self.getSino(img[j]) - sino[j])
            img = img - update

        return img
    
    def getSino(self, imgClean):
        #takes clean img and turns into a sinogram
        #vg = ts.volume(shape=(1, *imgClean.shape[1:]), size=(5, 300, 300))

        vg = ts.volume(shape=(1, *imgClean.shape[1:]), size=(300/imgClean.shape[1], 300, 300))
        # Define acquisition geometry. We want fan beam, so lets make a "cone" beam and make it 2D. We also need sod and sdd, so we set them up to something medically reasonable.
        pg = ts.cone(
            angles=360, shape=(1, 900), size=(1, 900), src_orig_dist=575, src_det_dist=1050
        )
        # A is now an operator.
        self.A = ts.operator(vg, pg)
        return self.A(imgClean)
