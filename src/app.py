import pickle
from flask import Flask
import flask
import os
import numpy as np
import umap
from sklearn import decomposition
from sklearn.preprocessing import StandardScaler
from facenet_pytorch import MTCNN, InceptionResnetV1

DATA_DIR = os.environ.get('DATA_DIR')

def load_pickled_features():
  print('Loading extracted features...')
  with open(f"{DATA_DIR}/pickles/wwzd_not_cropped_new_cpu.pickle", 'rb') as f:
    features = pickle.load(f)
  print('Features loaded')
  return features

def prepare_facenet_pytorch():
  print('Loading resnet and mtcnn')
  # Create an inception resnet (in eval mode):
  resnet = InceptionResnetV1(pretrained='vggface2').eval()
  mtcnn = MTCNN(post_process=False)
  print('CNNs loaded')
  return (resnet, mtcnn)

vectors_cpu = load_pickled_features()
vectors_cpu = sorted(vectors_cpu, key=lambda x: x[0])
resnet, mtcnn = prepare_facenet_pytorch()

just_vectors = [v[1].detach().numpy()[0] for v in vectors_cpu]

def calculate_dataset_metadata():
  ranges = {
    '000': [1, 999]
  }

  for i in range(1, 203):
      ranges[f'{i:03d}'] = [ i * 1000, (i+1)*1000 - 1]

  ranges['202'] = [202000, 202500]
  dataset_info = {
    'total': len(just_vectors),
    'ranges': ranges
  }

  return dataset_info

def extract_image_indexes_from_tilemap_range(start, end):
  first_set = f'{int(start):03d}'
  last_set = f'{int(end):03d}'
  start_idx = dataset_info['ranges'][first_set][0]
  end_idx = dataset_info['ranges'][last_set][1]
  return start_idx,end_idx

def get_tilemap_set(start, end):
  tilemaps = [
    f'{i:03d}' for i in range(int(start), int(end) + 1)
  ]
  
  return tilemaps

dataset_info = calculate_dataset_metadata()

isBusy = False

app = Flask(__name__)

@app.route('/status')
def get_status():
  return {
    'busy': isBusy
  }

@app.get('/dataset/info')
def get_dataset_info():
  return dataset_info

@app.route('/tilemaps/<id>')
def get_tilemap(id: str):
  return flask.send_from_directory(f"{DATA_DIR}/tilemaps", path=f'tilemap-{id}.jpg', as_attachment=False)

@app.get('/pca/<start>/<end>')
def get_pca_tilemap(start: str, end: str):
  global isBusy
  # i = int(tilemap)
  # start = i*1000
  # if i == 202:
  #   end = 202499
  # else:
  #   end = (i+1)*1000 - 1
  start_idx, end_idx = extract_image_indexes_from_tilemap_range(start, end)
  tilemaps = get_tilemap_set(start, end)
  X = np.array(just_vectors[start_idx:end_idx])

  X_std = StandardScaler().fit_transform(X)

  pca = decomposition.PCA(n_components=3)

  isBusy = True
  reduced = pca.fit_transform(X_std)
  isBusy = False

  return {
    'pca': reduced.tolist(),
    'total': len(reduced),
    'tilemap_ids': tilemaps
  }

@app.get('/umap/<int:start>/<int:end>')
def get_umap_tilemap(start: int, end: int):
  global isBusy
  # i = int(tilemap)
  # start = i*1000
  # if i == 202:
  #   end = 202499
  # else:
  #   end = (i+1)*1000 - 1
  
  start_idx, end_idx = extract_image_indexes_from_tilemap_range(start, end)
  tilemaps = get_tilemap_set(start, end)
  X = np.array(just_vectors[start_idx:end_idx])

  X_std = StandardScaler().fit_transform(X)

  umap_fit = umap.UMAP(n_components=3)

  isBusy = True
  reduced_umap = umap_fit.fit_transform(X_std)
  isBusy = False

  return {
    'umap': reduced_umap.tolist(),
    'total': len(reduced_umap),
    'tilemaps': tilemaps
  }


@app.before_request
def check_busy():
  if isBusy:
    return {
      'error': 'Server is busy, please wait'
    }, 503