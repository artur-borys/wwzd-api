# WWZD API
## Przed uruchomieniem
~~Musicie pobrać plik data.7z (link na messengerze) i wypakować go.
Jeśli będziecie odpalać plik docker-compose.yaml, to musi znajdować się w tym samym katalogu. Jeśli ręcznie budujecie obraz i odpalacie samym dockerem, to musicie odpowiednio podać ścieżkę absolutną do folderu i zamontować w kontenerze na ścieżce ``/data``.~~

Musicie pobrać plik data.7z (link na messengerze) i wypakować go do ``src/data``.

Wizualizacja:
```
src/
  data/
    pickles/
      celeba_features_pca_reduced.pickle
      celeba_features_umap_reduced.pickle
    tilemaps/
      tilemap-000.jpg
      ...
    models/
      resnet50_celeba/
        ...
  app.py
  Dockerfile
  ...
docker-compose.yaml
```

Obraz może ważyć około 4-5 GB.
## Uruchomienie
Najprościej przez docker-compose:
``` bash
docker-compose -f docker-compose.yaml up
```

Jak pojawi się aktualizacja, to trzeba wywołać:
``` bash
docker-compose -f docker-compose.yaml build
```

Więcej [tutaj](https://docs.docker.com/engine/reference/commandline/cli/) i [tutaj](https://docs.docker.com/compose/)

Pierwsze budowanie może trwać długo, w zależności od prędkości internetu. Każde kolejne powinno trwać krótko, chyba, że zostaną dodane nowe zależności w ``src/Pipfile``.

Serwer nasłuchuje na porcie 5000, więc wszelkie zapytania trzeba wysyłać na ``http://localhost:5000``. Jeśli ten port wam nie odpowiada, to możecie zmienić w ``docker-compose.yaml``:
``` yaml
services:
  wwzd_api:
    build: src/
    ports:
      - {port_hosta}:5000
    volumes:
      - ./data:/data
```
## Zajętość
Jeśli serwer jest aktualnie zajęty przetwarzaniem jakiegoś zapytania (UMAP może trwać nawet kilka minut), to zwróci odpowiedź HTTP 503
``` json
{
  "error": "Server is busy, please wait"
}
```

## Endpointy
### ``GET /status``
Zwraca status. Jeśli serwer nie jest zajęty, to zwraca HTTP 200:
``` json
{
  "busy": false
}
```

### ``GET /dataset/info``
Zwraca informacje o datasetcie, a konkretnie ilość zdjęć i id zakresów. Dataset jest podzielony na zakresy do 1000 zdjęć. Dla każdego takiego zakresu jest jedna tilemapa.

000: 0-999
001: 1000-1999
002: 2000-2999
...
202: 202000 - 202598

Przykładowa odpowiedź:
``` json
{
  "total": 202599,
  "ranges": {
    "000": [0, 999],
    "001": [1000, 1999],
    "002": [2000, 2999],
    ...
    "202": [202000, 202598] 
  }
}
```

### ``GET /tilemaps/{id}``
Zwraca plik graficzny z tilemapą dla zakresu o podanym ``id``.

Np. ``id = 000``

![](./tilemap-000.jpg)

Tilemapy mają tile o rozmiarach 48x48, ale zdjęcia nie są kwadratowe, więc wysokość jest 48px a szerokość inna.

Tilemapy należy odczytywać linijka po linijce, od lewej do prawej.

### ``GET /pca/{start}/{end}/standalone``
Endpoint przyjmuje parametry ``start`` i ``end``, które są początkowym i końcowym id zakresu. Czyli np. ``/pca/0/9/standalone`` zwróci nam wyniki dla zdjęć 0-9999 z datasetu, a `/pca/1/1/standalone` zdjęcia 1000-1999

Endpoint w odpowiedzi zwraca zredukowany metodą PCA wektor cech ze zbioru CelebA. Najpierw są wektory dla zdjęć z datasetu

Endpoint zwraca także listę id tilemapów, na którym są zdjęcia z podanych zakresów.

Przykładowa odpowiedź:
``` json
{
  "features": [
    [
      142.4803009033203,
      -1.541911244392395,
      20.09254264831543
    ],
    [
      -16.425695419311523,
      -3.1322970390319824,
      3.1832358837127686
    ],
    [
      -16.069305419921875,
      -3.0842366218566895,
      4.038396835327148
    ],
    ...
  ],
  "tilemap_ids": [
    "000",
    "001"
  ],
  "total": 2000
}
```

### ``GET /umap/{start}/{end}/standalone``
Jak wyżej, ale dla redukcji metodą UMAP.

### ``POST /dataset``
Endpoint do wysyłania nowego datasetu.
Treść zapytania to musi być ``form-data`` z jednym polem o nazwie ``file``, które zawiera plik ZIP.
W tym pliku muszą znajdować się bezpośrednio w top-level zdjęcia. Serwer przetworzy pierwsze 1000 zdjęć z głównego katalogu.

Serwer wypakowuje ZIP, generuje tilemapę, wyciąga i redukuje cechy obiema metodami, dlatego może to potrwać nawet kilka minut.

Po zakończeniu zwraca identyfikator datasetu, np:
```
70207d49d53ccdca5d5dfc91d006cd09
```

### ``GET /dataset/:hash/features/:reducer``
Zwraca zredukowany wektor cech za pomocą ``reducer`` (``pca`` lub ``umap``).
``hash`` to wspominany wcześniej identyfikator datasetu.

### ``GET /dataset/:hash/tilemap``
Zwraca tilemapę dla datasetu o podanym id. Tilemapa ma taką samą strukturę jak dla CelebA.