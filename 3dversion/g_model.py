from __future__ import division
import os
import time
from glob import glob
import tensorflow as tf
import numpy as np
from six.moves import xrange

from utils import *
from loss_functions import *
from scipy.misc import imsave

class MR2CT(object):
    def __init__(self, sess, batch_size=10, depth_MR=32, height_MR=32,
                 width_MR=32, depth_CT=32, height_CT=24,
                 width_CT=24, l_num=2, wd=0.0005, checkpoint_dir=None, path_patients_h5=None, learning_rate=2e-8):
        """
        Args:
            sess: TensorFlow session
            batch_size: The size of batch. Should be specified before training.
            output_size: (optional) The resolution in pixels of the images. [64]
            y_dim: (optional) Dimension of dim for y. [None]
            z_dim: (optional) Dimension of dim for Z. [100]
            gf_dim: (optional) Dimension of gen filters in first conv layer. [64]
            df_dim: (optional) Dimension of discrim filters in first conv layer. [64]
            gfc_dim: (optional) Dimension of gen units for for fully connected layer. [1024]
            dfc_dim: (optional) Dimension of discrim units for fully connected layer. [1024]
            c_dim: (optional) Dimension of image color. For grayscale input, set to 1. [3]
        """
        self.sess = sess
        self.l_num=l_num
        self.wd=wd
        self.learning_rate=learning_rate
        self.batch_size=batch_size       
        self.depth_MR=depth_MR
        self.height_MR=height_MR
        self.width_MR=width_MR
        self.depth_CT=depth_CT
        self.height_CT=height_CT
        self.width_CT=width_CT
        self.checkpoint_dir = checkpoint_dir
        self.data_generator = Generator_3D_patches(path_patients_h5,self.batch_size)
        self.build_model()

    def build_model(self):
    	self.inputMR=tf.placeholder(tf.float32, shape=[None, self.depth_MR, self.height_MR, self.width_MR, 1])
        self.CT_GT=tf.placeholder(tf.float32, shape=[None, self.depth_CT, self.height_CT, self.width_CT, 1])
        batch_size_tf = tf.shape(self.inputMR)[0]  #variable batchsize so we can test here
        self.train_phase = tf.placeholder(tf.bool, name='phase_train')
        self.G = self.generator(self.inputMR,batch_size_tf)
        print 'shape output G ',self.G.get_shape()
        self.global_step = tf.Variable(0, name='global_step', trainable=False)
        self.g_loss=lp_loss(self.G, self.CT_GT, self.l_num, batch_size_tf)
        print 'learning rate ',self.learning_rate
        #self.g_optim =tf.train.AdamOptimizer(self.learning_rate).minimize(self.g_loss)
        #tf.train.GradientDescentOptimizer(self.learning_rate).minimize(self.g_loss)
        self.merged = tf.merge_all_summaries()
        self.writer = tf.train.SummaryWriter("./summaries", self.sess.graph)
        self.saver = tf.train.Saver()


    def generator(self,inputMR,batch_size_tf):        
        
        ######## FCN for the 32x32x32 to 24x24x24 , added dilaion by yourself####################################        
        conv1_a = conv_op_3d_bn(inputMR, name="conv1_a", kh=5, kw=5, kz=5,  n_out=48, dh=1, dw=1, dz=1, wd=self.wd, padding='VALID',train_phase=self.train_phase)#30
        conv2_a = conv_op_3d_bn(conv1_a, name="conv2_a", kh=3, kw=3, kz=3,  n_out=96, dh=1, dw=1, dz=1, wd=self.wd, padding='SAME',train_phase=self.train_phase)
        conv3_a = conv_op_3d_bn(conv2_a, name="conv3_a", kh=3, kw=3, kz=3,  n_out=128, dh=1, dw=1, dz=1, wd=self.wd, padding='SAME',train_phase=self.train_phase)#28
        conv4_a = conv_op_3d_bn(conv3_a, name="conv4_a", kh=5, kw=5, kz=5,  n_out=96, dh=1, dw=1, dz=1, wd=self.wd, padding='VALID',train_phase=self.train_phase)
        conv5_a = conv_op_3d_bn(conv4_a, name="conv5_a", kh=3, kw=3, kz=3,  n_out=48, dh=1, dw=1, dz=1, wd=self.wd, padding='SAME',train_phase=self.train_phase)#26
        conv6_a = conv_op_3d_bn(conv5_a, name="conv6_a", kh=3, kw=3, kz=3,  n_out=32, dh=1, dw=1, dz=1, wd=self.wd, padding='SAME',train_phase=self.train_phase)
        #conv7_a = conv_op_3d_bn(conv6_a, name="conv7_a", kh=3, kw=3, kz=3,  n_out=1, dh=1, dw=1, dz=1, wd=self.wd, padding='SAME',train_phase=self.train_phase)#24
        conv7_a = conv_op_3d_norelu(conv6_a, name="conv7_a", kh=3, kw=3, kz=3,  n_out=1, dh=1, dw=1, dz=1, wd=self.wd, padding='SAME')#24 I modified it here,dong
        self.MR_16_downsampled=conv7_a#JUST FOR TEST
        return conv7_a




    def train(self, config):
    	path_test='/home/dongnie/warehouse/prostate/ganData64to24Test'
        print 'global_step ', self.global_step.name
        print 'trainable vars '
        for v in tf.trainable_variables():
            print v.name

        if self.load(self.checkpoint_dir):
            print(" [*] Load SUCCESS")
        else:
            print(" [!] Load failed...")
            self.sess.run(tf.initialize_all_variables())
        temp = set(tf.all_variables())
        start = self.global_step.eval() # get last global_step
        print("Start from:", start)

        ############ This is for only initializing adam vars####################
        temp = set(tf.all_variables())
        self.g_optim =tf.train.AdamOptimizer(self.learning_rate).minimize(self.g_loss)
        self.sess.run(tf.initialize_variables(set(tf.all_variables()) - temp))
        print("Start after adam (should be the same):", start)
        #####################################

        for it in range(start,config.iterations):

            X,y=self.data_generator.next()
            

            # Update G network
            _, loss_eval, layer_out_eval = self.sess.run([self.g_optim, self.g_loss, self.MR_16_downsampled],
                        feed_dict={ self.inputMR: X, self.CT_GT:y, self.train_phase: True })
            self.global_step.assign(it).eval() # set and update(eval) global_step with index, i
            

            if it%config.show_every==0:#show loss every show_every its
                print 'it ',it,'loss ',loss_eval
                print 'layer min ', np.min(layer_out_eval)
                print 'layer max ', np.max(layer_out_eval)
                print 'layer mean ', np.mean(layer_out_eval)
             #    print 'trainable vars ' 
            	# for v in tf.trainable_variables(): 
	            #     print v.name 
	            #     data_var=self.sess.run(v) 
	            #     grads = tf.gradients(self.g_loss, v) 
	            #     var_grad_val = self.sess.run(grads, feed_dict={self.inputMR: X, self.CT_GT:y }) 
	            #     print 'grad min ', np.min(var_grad_val) 
	            #     print 'grad max ', np.max(var_grad_val) 
	            #     print 'grad mean ', np.mean(var_grad_val) 
	            #     #print 'shape ',data_var.shape 
	            #     print 'filter min ', np.min(data_var) 
	            #     print 'filter max ', np.max(data_var) 
	            #     print 'filter mean ', np.mean(data_var)    
	                #self.writer.add_summary(summary, it)
                            # print 'trainable vars ' 

            
            if it%config.test_every==0 and it!=0:#==0:#test one subject                

                mr_test_itk=sitk.ReadImage(os.path.join(path_test,'prostate_1to1_MRI.nii'))
                ct_test_itk=sitk.ReadImage(os.path.join(path_test,'prostate_1to1_CT.nii'))
                mrnp=sitk.GetArrayFromImage(mr_test_itk)
                #mu=np.mean(mrnp)
                #mrnp=(mrnp-mu)/(np.max(mrnp)-np.min(mrnp))
                ctnp=sitk.GetArrayFromImage(ct_test_itk)
                print mrnp.dtype
                print ctnp.dtype
                ct_estimated=self.test_1_subject(mrnp,ctnp,[32,32,32],[24,24,24],[5,5,2])
                psnrval=psnr(ct_estimated,ctnp)
                print ct_estimated.dtype
                print ctnp.dtype
                print 'psnr= ',psnrval
                volout=sitk.GetImageFromArray(ct_estimated)
                sitk.WriteImage(volout,'ct_estimated_{}'.format(it)+'.nii.gz')

            if it%config.save_every==0:#save weights every save_every iterations
                self.save(self.checkpoint_dir, it)

    def evaluate(self,patch_MR):
        """ patch_MR is a np array of shape [H,W,nchans]
        """
        patch_MR=np.expand_dims(patch_MR,axis=0)#[1,H,W,nchans]
        patch_MR=np.expand_dims(patch_MR,axis=4)#[1,H,W,nchans]

        patch_CT_pred, MR16_eval= self.sess.run([self.G,self.MR_16_downsampled],
                        feed_dict={ self.inputMR: patch_MR, self.train_phase: False})

        patch_CT_pred=np.squeeze(patch_CT_pred)#[Z,H,W]
        #imsave('mr32.png',np.squeeze(MR16_eval[0,:,:,2]))
        #imsave('ctpred.png',np.squeeze(patch_CT_pred[0,:,:,0]))
        #print 'mean of layer  ',np.mean(MR16_eval)
        #print 'min ct estimated ',np.min(patch_CT_pred)
        #print 'max ct estimated ',np.max(patch_CT_pred)
        #print 'mean of ctpatch estimated ',np.mean(patch_CT_pred)
        return patch_CT_pred


    def test_1_subject(self,MR_image,CT_GT,MR_patch_sz,CT_patch_sz,step):
        """
            receives an MR image and returns an estimated CT image of the same size
        """
        matFA=MR_image
        matSeg=CT_GT
        dFA=MR_patch_sz
        dSeg=CT_patch_sz

        eps=1e-5
        [row,col,leng]=matFA.shape
        margin1=int((dFA[0]-dSeg[0])/2)
        margin2=int((dFA[1]-dSeg[1])/2)
        margin3=int((dFA[2]-dSeg[2])/2)
        cubicCnt=0
        marginD=[margin1,margin2,margin3]
        print 'matFA shape is ',matFA.shape
        matFAOut=np.zeros([row+2*marginD[0],col+2*marginD[1],leng+2*marginD[2]])
        print 'matFAOut shape is ',matFAOut.shape
        matFAOut[marginD[0]:row+marginD[0],marginD[1]:col+marginD[1],marginD[2]:leng+marginD[2]]=matFA

        # matFAOut[0:marginD[0],marginD[1]:col+marginD[1],marginD[2]:leng+marginD[2]]=matFA[0:marginD[0],:,:] #we'd better flip it along the first dimension
        # matFAOut[row+marginD[0]:matFAOut.shape[0],marginD[1]:col+marginD[1],marginD[2]:leng+marginD[2]]=matFA[row-marginD[0]:matFA.shape[0],:,:] #we'd better flip it along the 1st dimension

        # matFAOut[marginD[0]:row+marginD[0],0:marginD[1],marginD[2]:leng+marginD[2]]=matFA[:,0:marginD[1],:] #we'd better flip it along the 2nd dimension
        # matFAOut[marginD[0]:row+marginD[0],col+marginD[1]:matFAOut.shape[1],marginD[2]:leng+marginD[2]]=matFA[:,col-marginD[1]:matFA.shape[1],:] #we'd better to flip it along the 2nd dimension

        # matFAOut[marginD[0]:row+marginD[0],marginD[1]:col+marginD[1],0:marginD[2]]=matFA[:,:,0:marginD[2]] #we'd better flip it along the 3rd dimension
        # matFAOut[marginD[0]:row+marginD[0],marginD[1]:col+marginD[1],marginD[2]+leng:matFAOut.shape[2]]=matFA[:,:,leng-marginD[2]:matFA.shape[2]]

        if margin1!=0:
            matFAOut[0:marginD[0],marginD[1]:col+marginD[1],marginD[2]:leng+marginD[2]]=matFA[marginD[0]-1::-1,:,:] #reverse 0:marginD[0]
            matFAOut[row+marginD[0]:matFAOut.shape[0],marginD[1]:col+marginD[1],marginD[2]:leng+marginD[2]]=matFA[matFA.shape[0]-1:row-marginD[0]-1:-1,:,:] #we'd better flip it along the 1st dimension
        if margin2!=0:
            matFAOut[marginD[0]:row+marginD[0],0:marginD[1],marginD[2]:leng+marginD[2]]=matFA[:,marginD[1]-1::-1,:] #we'd flip it along the 2nd dimension
            matFAOut[marginD[0]:row+marginD[0],col+marginD[1]:matFAOut.shape[1],marginD[2]:leng+marginD[2]]=matFA[:,matFA.shape[1]-1:col-marginD[1]-1:-1,:] #we'd flip it along the 2nd dimension
        if margin3!=0:
            matFAOut[marginD[0]:row+marginD[0],marginD[1]:col+marginD[1],0:marginD[2]]=matFA[:,:,marginD[2]-1::-1] #we'd better flip it along the 3rd dimension
            matFAOut[marginD[0]:row+marginD[0],marginD[1]:col+marginD[1],marginD[2]+leng:matFAOut.shape[2]]=matFA[:,:,matFA.shape[2]-1:leng-marginD[2]-1:-1]
        


        matOut=np.zeros((matSeg.shape[0],matSeg.shape[1],matSeg.shape[2]))
        used=np.zeros((matSeg.shape[0],matSeg.shape[1],matSeg.shape[2]))+eps
        #fid=open('trainxxx_list.txt','a');
        for i in range(0,row-dSeg[0],step[0]):
            for j in range(0,col-dSeg[1],step[1]):
                for k in range(0,leng-dSeg[2],step[2]):
                    volSeg=matSeg[i:i+dSeg[0],j:j+dSeg[1],k:k+dSeg[2]]
                    #print 'volSeg shape is ',volSeg.shape
                    volFA=matFAOut[i:i+dSeg[0]+2*marginD[0],j:j+dSeg[1]+2*marginD[1],k:k+dSeg[2]+2*marginD[2]]
                    #print 'volFA shape is ',volFA.shape
                    #mynet.blobs['dataMR'].data[0,0,...]=volFA
                    #mynet.forward()
                    #temppremat = mynet.blobs['softmax'].data[0].argmax(axis=0) #Note you have add softmax layer in deploy prototxt
                    temppremat=self.evaluate(volFA)
                    #print 'patchout shape ',temppremat.shape
                    #temppremat=volSeg
                    matOut[i:i+dSeg[0],j:j+dSeg[1],k:k+dSeg[2]]=matOut[i:i+dSeg[0],j:j+dSeg[1],k:k+dSeg[2]]+temppremat;
                    used[i:i+dSeg[0],j:j+dSeg[1],k:k+dSeg[2]]=used[i:i+dSeg[0],j:j+dSeg[1],k:k+dSeg[2]]+1;
        matOut=matOut/used
        return matOut


            
    def save(self, checkpoint_dir, step):
        model_name = "MR2CT.model"
        
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)

        self.saver.save(self.sess,
                        os.path.join(checkpoint_dir, model_name),
                        global_step=step)

    def load(self, checkpoint_dir):
        print(" [*] Reading checkpoints...")

        ckpt = tf.train.get_checkpoint_state(checkpoint_dir)
        if ckpt and ckpt.model_checkpoint_path:
            ckpt_name = os.path.basename(ckpt.model_checkpoint_path)
            self.saver.restore(self.sess, ckpt.model_checkpoint_path)
            return True
        else:
            return False
