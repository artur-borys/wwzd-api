import pickle
from flask import Flask, request
import flask
from flask_cors import CORS
import os
import numpy as np
import umap
import cv2
from sklearn import decomposition
from sklearn.preprocessing import StandardScaler
from facenet_pytorch import MTCNN, InceptionResnetV1
from torchvision import transforms
from werkzeug.utils import secure_filename

DATA_DIR = os.environ.get('DATA_DIR')
ALLOWED_EXTENSIONS = ['png', 'jpg', 'bmp', 'jpeg']

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

def extract_image_features(filepath):
  img = cv2.imread(filepath)
  im = np.asarray(img)
  img_tensor = mtcnn(im)

  if img_tensor is None:
    img_tensor = transforms.ToTensor()(im)
  
  img_embeddings = resnet(img_tensor.unsqueeze(0))
  return img_embeddings.detach().numpy()[0]

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


@app.post('/pca/<start>/<end>')
def get_pca_tilemap(start: str, end: str):
  global isBusy
  filepath = handle_file_upload()
  if not filepath:
    return {"error": "Error during file upload"}, 400

  img_features = extract_image_features(filepath)

  start_idx, end_idx = extract_image_indexes_from_tilemap_range(start, end)
  tilemaps = get_tilemap_set(start, end)
  features = just_vectors[start_idx:end_idx]
  features.append(img_features)
  X = np.array(features)

  X_std = StandardScaler().fit_transform(X)

  pca = decomposition.PCA(n_components=3)

  isBusy = True
  reduced = pca.fit_transform(X_std)
  isBusy = False

  return {
      'features': reduced.tolist(),
      'total': len(reduced),
      'tilemap_ids': tilemaps
  }

@app.get('/pca/<start>/<end>/standalone')
def get_pca_tilemap_standalone(start: str, end: str):
  global isBusy
  
  start_idx, end_idx = extract_image_indexes_from_tilemap_range(start, end)
  tilemaps = get_tilemap_set(start, end)
  features = just_vectors[start_idx:end_idx]

  X = np.array(features)

  X_std = StandardScaler().fit_transform(X)

  pca = decomposition.PCA(n_components=3)

  isBusy = True
  reduced = pca.fit_transform(X_std)
  isBusy = False

  return {
    'features': reduced.tolist(),
    'total': len(reduced),
    'tilemap_ids': tilemaps
  }

@app.post('/umap/<int:start>/<int:end>')
def get_umap_tilemap(start: int, end: int):
  global isBusy
  filepath = handle_file_upload()
  if not filepath:
    return { "error": "Error during file upload" }, 400
  
  img_features = extract_image_features(filepath)
  
  start_idx, end_idx = extract_image_indexes_from_tilemap_range(start, end)
  tilemaps = get_tilemap_set(start, end)
  features = just_vectors[start_idx:end_idx]
  features.append(img_features)
  X = np.array(features)

  X_std = StandardScaler().fit_transform(X)

  umap_fit = umap.UMAP(n_components=3)

  isBusy = True
  reduced_umap = umap_fit.fit_transform(X_std)
  isBusy = False

  return {
    'features': reduced_umap.tolist(),
    'total': len(reduced_umap),
    'tilemaps': tilemaps
  }


@app.get('/umap/<int:start>/<int:end>/standalone')
def get_umap_tilemap_standalone(start: int, end: int):
  global isBusy
  
  start_idx, end_idx = extract_image_indexes_from_tilemap_range(start, end)
  tilemaps = get_tilemap_set(start, end)
  features = just_vectors[start_idx:end_idx]

  X = np.array(features)

  X_std = StandardScaler().fit_transform(X)

  umap_fit = umap.UMAP(n_components=3)

  isBusy = True
  reduced_umap = umap_fit.fit_transform(X_std)
  isBusy = False

  return {
      'features': reduced_umap.tolist(),
      'total': len(reduced_umap),
      'tilemaps': tilemaps
  }


@app.before_request
def check_busy():
  if isBusy:
    return {
      'error': 'Server is busy, please wait'
    }, 503
