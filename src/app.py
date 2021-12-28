import pickle
from flask import Flask, request
import flask
from flask_cors import CORS
import os
import subprocess
import numpy as np
import tensorflow as tf
from sklearn import decomposition
from sklearn.preprocessing import StandardScaler
import umap
from werkzeug.utils import secure_filename
import zipfile
import tempfile
import hashlib
import traceback
import logging

logging.basicConfig(level=logging.INFO)

DATA_DIR = os.environ.get('DATA_DIR')
ALLOWED_EXTENSIONS = ['zip']

def load_pickled_features():
  logging.info('Loading extracted features...')
  logging.info('Reduced with PCA...')
  with open(f"{DATA_DIR}/pickles/celeba_features_pca_reduced.pickle", 'rb') as f:
    features_pca = pickle.load(f)
  logging.info('Reduced with PCA loaded')
  logging.info('Reduced with UMAP...')
  with open(f"{DATA_DIR}/pickles/celeba_features_umap_reduced.pickle", 'rb') as f:
    features_umap = pickle.load(f)
  logging.info('Reduced with UMAP loaded')
  logging.info('Features loaded')
  return features_pca, features_umap

def load_model():
  logging.info("Loading ResNet50 CelebA model")
  model = tf.keras.models.load_model(f"{DATA_DIR}/models/resnet50_celeba")
  logging.info("Model loaded")
  return model

features_pca, features_umap = load_pickled_features()
resnet50_celeba = load_model()

datasets_map = dict()

def calculate_dataset_metadata():
  ranges = {}

  for i in range(0, 203):
      ranges[f'{i:03d}'] = [ i * 1000, (i+1)*1000 - 1]

  ranges['202'] = [202000, 202598]
  dataset_info = {
    'total': len(features_pca),
    'ranges': ranges
  }

  return dataset_info

def extract_image_indexes_from_tilemap_range(start, end):
  first_set = f'{int(start):03d}'
  last_set = f'{int(end):03d}'
  start_idx = dataset_info['ranges'][first_set][0]
  end_idx = dataset_info['ranges'][last_set][1] + 1
  return start_idx,end_idx

def get_tilemap_set(start, end):
  tilemaps = [
    f'{i:03d}' for i in range(int(start), int(end) + 1)
  ]
  
  return tilemaps

def allowed_file(filename):
    return '.' in filename and \
     filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def handle_file_upload():
  if 'file' not in request.files:
    return False
  file = request.files['file']
  if file.filename == '':
    return False

  if file and allowed_file(file.filename):
    filename = secure_filename(file.filename)
    filepath = os.path.join("/tmp", filename)
    file.save(filepath)
    return filepath
  return False

def extract_images(filepath, dataset_dir):
  images_dir = os.path.join(dataset_dir, 'images')
  with zipfile.ZipFile(filepath, 'r') as z:
    z.extractall(path=images_dir)
    for _, _, files in os.walk(images_dir):
      for i, file in enumerate(sorted(files)):
        if i < 1000:
          _, extension = os.path.splitext(file)
          os.rename(os.path.join(images_dir, file), os.path.join(images_dir, f'{i:0>4}{extension}'))
        else:
          os.remove(os.path.join(images_dir, file))


def extract_features_from_images(imagesdir):
  dataset = tf.keras.utils.image_dataset_from_directory(imagesdir, labels=None, image_size=(224, 224))
  return resnet50_celeba.predict(dataset)

def standardize_features(features):
  standardizer = StandardScaler()
  return standardizer.fit_transform(features)

def reduce_features_pca(features):
  pca = decomposition.PCA(n_components=3)
  return pca.fit_transform(features)

def reduce_features_umap(features):
  umap_reducer = umap.UMAP(n_components=3)
  return umap_reducer.fit_transform(features)

def generate_tilemap(dataset_dir):
  IMAGES_DIR = os.path.join(dataset_dir, 'images')
  TILES_DIR = os.path.join(dataset_dir, 'tiles')
  try:
    os.rmdir(TILES_DIR)
  except:
    pass
  os.mkdir(TILES_DIR)
  p = subprocess.Popen(["bash", "-c", f"montage {IMAGES_DIR}/* -tile 10x100 -geometry 48x48+1+1 {TILES_DIR}/tilemap.jpg"])
  exit_code = p.wait()
  return exit_code == 0

def handle_dataset(filepath):
  try:
    dataset_dir = tempfile.mkdtemp()
    images_dir = os.path.join(dataset_dir, 'images')
    os.mkdir(images_dir)
    logging.info("Extracting ZIP file...")
    extract_images(filepath, dataset_dir)
    logging.info("ZIP extracted")
    logging.info("Generating tilemap...")
    if not generate_tilemap(dataset_dir):
      raise Exception("Failed to generate tilemap")
    logging.info("Tilemap generated")
    logging.info("Extracting and reducing features...")
    features_std = standardize_features(extract_features_from_images(images_dir))
    reduced_pca = reduce_features_pca(features_std)
    reduced_umap = reduce_features_umap(features_std)
    
    with open(os.path.join(dataset_dir, 'features_pca_reduced.pickle'), 'wb') as f:
      pickle.dump(reduced_pca, f)
    with open(os.path.join(dataset_dir, 'features_umap_reduced.pickle'), 'wb') as f:
      pickle.dump(reduced_umap, f)
    logging.info("Features extracted and persisted")
    dataset_hash = hashlib.md5(dataset_dir.encode()).digest().hex()
    datasets_map[dataset_hash] = dataset_dir
    logging.info(f"Added new dataset: {dataset_hash} = {dataset_dir}")
    return dataset_hash
  except Exception:
    traceback.print_exc()
    return False


dataset_info = calculate_dataset_metadata()

isBusy = False

app = Flask(__name__)

CORS(app)

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

@app.get('/pca/<start>/<end>/standalone')
def get_pca_tilemap_standalone(start: str, end: str):
  global isBusy
  
  start_idx, end_idx = extract_image_indexes_from_tilemap_range(start, end)
  tilemaps = get_tilemap_set(start, end)
  features = features_pca[start_idx:end_idx]

  return {
    'features': features.tolist(),
    'total': len(features),
    'tilemap_ids': tilemaps
  }

@app.get('/umap/<int:start>/<int:end>/standalone')
def get_umap_tilemap_standalone(start: int, end: int):
  global isBusy
  
  start_idx, end_idx = extract_image_indexes_from_tilemap_range(start, end)
  tilemaps = get_tilemap_set(start, end)
  features = features_umap[start_idx:end_idx]

  return {
      'features': features.tolist(),
      'total': len(features),
      'tilemaps': tilemaps
  }

@app.post('/dataset')
def post_dataset():
  isBusy = True
  filepath = handle_file_upload()
  if not filepath:
    logging.error("Wrong file")
    return {"error": "Error during file upload"}, 400
  dataset_hash = handle_dataset(filepath)
  if not dataset_hash:
    logging.error("Error during handling dataset")
    return {"error": "Error during handling dataset"}, 400
  isBusy = False
  return dataset_hash

@app.get('/dataset/<string:hash>/features/<string:reducer>')
def get_dataset_reduced(hash: str, reducer: str):
  if reducer not in ['pca', 'umap']:
    return {"error": "Invalid reducing method. Available: pca, umap"}, 400
  if hash not in datasets_map.keys():
    return {"error": "Dataset not found"}, 404
  dataset_dir = datasets_map[hash]

  with open(os.path.join(dataset_dir, f'features_{reducer}_reduced.pickle'), 'rb') as f:
    features = pickle.load(f)
  
  return {
    'features': features.tolist(),
    'total': len(features)
  }

@app.get('/dataset/<string:hash>/tilemap')
def get_dataset_tiles(hash: str):
  if hash not in datasets_map.keys():
    return {"error": "Dataset not found"}, 404
  dataset_dir = datasets_map[hash]
  return flask.send_from_directory(f"{dataset_dir}/tiles", path=f'tilemap.jpg', as_attachment=False)
  

@app.before_request
def check_busy():
  if isBusy:
    return {
      'error': 'Server is busy, please wait'
    }, 503
