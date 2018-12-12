import os, json, argparse
from threading import Thread
from Queue import Queue
import string
import numpy as np
from scipy.misc import imread, imresize
import h5py

"""
Create an HDF5 file of images for training a feedforward style transfer model.
"""

parser = argparse.ArgumentParser()

parser.add_argument('--train_x_dir', default='data/CACD/CACD2000_rotate_rename_new')
parser.add_argument('--train_image_list_x', default='data/CACD/cacd_cross_validating_list_2018/image_list_disorder_5fold2_old_train.txt')
parser.add_argument('--val_x_dir', default='data/CACD/CACD2000_rotate_rename_new')
parser.add_argument('--val_image_list_x', default='data/CACD/cacd_cross_validating_list_2018/image_list_disorder_5fold2_old_test.txt')
parser.add_argument('--output_file', default='data/CACD/CACD_2018_5fold2_old.h5')

parser.add_argument('--height', type=int, default=224)
parser.add_argument('--width', type=int, default=224)
parser.add_argument('--max_images', type=int, default=-1)
parser.add_argument('--num_workers', type=int, default=2)
parser.add_argument('--include_val', type=int, default=1)
parser.add_argument('--max_resize', default=16, type=int)
args = parser.parse_args()


def add_data(h5_file, image_dir, image_list_file, prefix, args):
  # Make a list of all images in the source directory
  image_list = []
  labels = []
  file = open(image_list_file)
  for line in file:
    filename = line.split()[0]
    agegroup = string.atoi(line.split()[2])
    print 'File name: %s ' % (filename)
    print 'Age Group: %d ' % (agegroup)
    image_list.append(os.path.join(image_dir, filename))
    labels.append(agegroup)
  num_images = len(image_list)

  # Resize all images and copy them into the hdf5 file
  # We'll bravely try multithreading
  dset_name = os.path.join(prefix, 'images')
  lset_name = os.path.join(prefix, 'labels')
  dset_size = (num_images, 3, args.height, args.width)
  lset_size = (num_images, 1)
  imgs_dset = h5_file.create_dataset(dset_name, dset_size, np.uint8)
  labels_dset = h5_file.create_dataset(lset_name, lset_size, np.int)
  
  # input_queue stores (idx, filename, agegroup) tuples,
  # output_queue stores (idx, resized_img, agegroup) tuples
  input_queue = Queue()
  output_queue = Queue()
  
  # Read workers pull images off disk and resize them
  def read_worker():
    while True:
      idx, filename, agegroup = input_queue.get()
      img = imread(filename)
  
      try:
        # First crop the image so its size is a multiple of max_resize
        H, W = img.shape[0], img.shape[1]
        H_crop = H - H % args.max_resize
        W_crop = W - W % args.max_resize
        img = img[:H_crop, :W_crop]
        img = imresize(img, (args.height, args.width))
      except (ValueError, IndexError) as e:
	    print idx
	    print filename
	    print agegroup
	    print img.shape, img.dtype
	    print e
      input_queue.task_done()
	  
      output_queue.put((idx, img, agegroup))
  
  # Write workers write resized images to the hdf5 file
  def write_worker():
    num_written = 0
    while True:
      idx, img, agegroup = output_queue.get()
      if img.ndim == 3:
        # RGB image, transpose from H x W x C to C x H x W
        imgs_dset[idx] = img.transpose(2, 0, 1)
        labels_dset[idx] = agegroup 
      elif img.ndim == 2:
        # Grayscale image; it is H x W so broadcasting to C x H x W will just copy
        # grayscale values into all channels.
        imgs_dset[idx] = img
        labels_dset[idx] = agegroup 
      output_queue.task_done()
      num_written = num_written + 1
      if num_written % 100 == 0:
        print 'Copied %d / %d images' % (num_written, num_images)
  
  # Start the read workers.
  for i in xrange(args.num_workers):
    t = Thread(target=read_worker)
    t.daemon = True
    t.start()
    
  # h5py locks internally, so we can only use a single write worker =(
  t = Thread(target=write_worker)
  t.daemon = True
  t.start()
    
  for idx, filename in enumerate(image_list):
    if args.max_images > 0 and idx >= args.max_images: break
    input_queue.put((idx, filename, labels[idx]))
    
  input_queue.join()
  output_queue.join()
  
  
  
if __name__ == '__main__':
  
  with h5py.File(args.output_file, 'w') as f:
    add_data(f, args.train_x_dir, args.train_image_list_x, 'train_x', args)
 
    if args.include_val != 0:
	add_data(f, args.val_x_dir, args.val_image_list_x, 'val_x', args)
