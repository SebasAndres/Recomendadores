from pyspark import SparkContext, SparkConf
from pyspark.sql import SQLContext, DataFrame
from pyspark.sql.functions import lit
from pyspark.sql.functions import split, explode, monotonically_increasing_id

import numpy as np
from numpy import linalg as LA
from scipy.sparse import csr_matrix

import json
import datetime
from tqdm.notebook import trange, tqdm

## TODO:
# - Implementar es_recommendation:
# -     Reemplazar variables locales de item_indexes y user_indexes por el indice en es_recommendation
# -     Hacer update_item_viewers en elastic.py, que actualice el indice de items correspondiente en elastic_search

from sar.models.elastic import ElasticHelper
from sar.models.hilfe import Utils

class SAR():

    # Inicializo el modelo
    def __init__(self, es_recommendation, es_metadata, TIME_SCORING=(17/3)*10**8, W_SCORING=1):

        # elastic search con la metadata
        self.es_helper = ElasticHelper(es_recommendation, es_metadata)

        # Matrices del modelo
        self.A = None
        self.C = None
        self.S = None

        pass
    
    def load_new_users(self, dataset, verb=False):
        # Dado un dataset, 
        # cargar los usuarios nuevos a los indices del modelo

        # obtengo los usuarios unicos del dataset
        users_in_ds:set = set([u.user_id for u in dataset.select("user_id").collect()])
        users_in_ds:list = list(users_in_ds)
        
        # cantidad de user_ids ignorados
        ignored:int = 0 
        
        for i in trange(len(users_in_ds)):
            userid = users_in_ds[i]
            if userid not in self.user_indexes.keys():
                index = len(self.user_indexes)
                # agrego al usuario al indice recommendation de es
                self.es_helper.add_user(userid, index)
            else:
                ignored += 1
        
        if verb:
            print("* (pre) N° de usuarios únicos: ", len(self.user_indexes.keys()))
            print("* (post) N° de usuarios únicos: ", len(self.user_indexes.keys()))
            print("* Diferencia de usuarios: ", len(self.user_indexes) - ignored)

        return ignored

    def load_new_items(self, dataset, verb=False):        
        # Dado un dataset,
        # cargar los items nuevos a los indices del modelo
    
        # cantidad de items antes de arrancar el ciclo
        n_items_pre = self.es_helper.n_items_in_recommendation()

        # info de items omitidos
        info:dict = { "missing_metadata": [] }

        # obtengo los items unicos del dataset
        items_in_ds = set([i.group_id for i in dataset.select("group_id").collect()])
        items_in_ds = list(items_in_ds)
        
        for j in trange(len(items_in_ds)):

            itemid = items_in_ds[j] 
            
            if itemid not in self.item_indexes.keys():
            
                # el index es por aparicion
                index = len(self.item_indexes)
                
                # leo la metadata segun el group_id
                metadata = self.es_metadata.get_item_metadata(itemid)
                
                # solo agrego items que tengan metadata
                if metadata == dict():
                    info["missing_metadata"].append(itemid)            
                else:
                    self.es_helper.add_item(itemid, index)

        if verb:
            print("* (pre) N° de items únicos: ", len(self.item_indexes.keys()))
            print("* (post) N° de items únicos: ", len(self.item_indexes.keys()))
            print("* Diferencia de items: ", len(self.item_indexes.keys()) - n_items_pre)
            print("* Items omitidos: ", len(info["missing_metadata"]))    
        
        return info

    def build_coocurrence_matrix(self) -> csr_matrix:

        M:int = self.es_helper.n_items_in_recommendation() # n items en el es_recommendation
        C:csr_matrix = csr_matrix((M,M)).tolil()
                   
        for i, item_i in enumerate(M):
            
            index_i:int = self.es_metadata.get_item_index(item_i) # index del item i
            item_i_viewers:set = self.es_metadata.get_item_viewers(item_i) # usuarios que vieron el item i

            for j, item_j in enumerate(M):
                
                index_j:int = self.es_metadata.get_item_index(item_j) # index del item j
                item_j_viewers:set = self.es_metadata.get_item_viewers(item_j) # usuarios que vieron el item j
                
                C[index_j, index_i] = len(item_j_viewers.intersection(item_i_viewers))
            
        return C

    def build_similarity_matrix(self) -> csr_matrix:
        return self.C

    def scoring_function(self, event_time) -> float:           
        t_k = event_time.timestamp()
        t_0 = datetime.datetime.now().timestamp()
        exp = - (t_0 - t_k) / self.T
        return self.W * 2 ** exp

    def build_affinity_matrix(self, dataset) -> csr_matrix:      
        # Dado un dataset, actualiza la matriz A
                         
        M = self.es_helper.n_items_in_recommendation()   
        N = self.es_helper.n_users_in_recommendation()
        
        self.A:csr_matrix = csr_matrix((N, M)).tolil()  
        ignored:int = 0
        
        for interaction in dataset.collect():            
            user_id, group_id, event_time = Utils.decode_interaction(interaction)
            
            if self.es_helper.is_valid_group_id(group_id) and self.es_helper.is_valid_user_id(user_id):    
                index_item = self.es_helper.get_item_index(group_id)
                index_user = self.es_helper.get_user_index(user_id)
                self.A[index_user, index_item] += self.scoring_function(event_time)
            else:
                ignored += 1
                    
        return ignored        

    def fit(self, dataset):
        # Dado un dataset, actualiza las matrices C, S, A
        
        # actualiza el indice con las vistas por item
        self.es_metadata.update_items_viewers(dataset)
        
        # actualizo las matrices 
        self.C = self.build_coocurrence_matrix()
        self.S = self.build_similarity_matrix()
        self.A = self.build_affinity_matrix()

        # armo la matriz de predicciones 
        self.Y = self.A @ self.S

        pass
    
    def recommend_similar_k_items(self,
                                  group_id,
                                  k:int,
                                  include=[],
                                  exclude=[],
                                  enhance=[]):
        
        # Dado un group_id y ...
        # Recomendar los k items mas similares
        
        itemIndex = self.es_helper.get_item_index(group_id)
    
        item2item:list = [
            (similarity, i) for i, similarity in enumerate(list(self.S[itemIndex].toarray()[0]))
        ]    
            
        # eliminamos al elemento del que se buscan los similares
        item2item.pop(itemIndex)
        
        ## filtro y enhance
        BIAS = 10
        for _, index in item2item:
            item_metadata = self.es_metadata.get_item_metadata(index, index=True)
            
            # filtrar
            if item_metadata["filtros"] not in include:
                item2item[index] = -1
            
            # potenciar
            if item_metadata["filtros"] in enhance:
                item2item[index] += BIAS
            
            pass
        
        # ordeno los items
        ordered_items = sorted(item2item, key=lambda x: x[0], reverse=True)
        recommendations:list = ordered_items[:k]

        # hay items con scoring 0?
        l = sum([1 for scoring, index in recommendations if scoring == 0])
        
        if l > 0:
            # agrego l items populares a recommendations
            recommendations = recommendations[:k-l]
            # recommendations.extend(getTopLMovies(self.Y, l, exclude=exclude))

        # los dejo en el formato valido 
        top_k:list = []
        for n_views, index in recommendations:
            rec = (self.es_helper.get_group_id[index], n_views)
            top_k.append(rec)
        
        return top_k

    def recommend_k_items_to_user(self, user_id):
        # Dado un user_id y ...
        # Recomendar los k items con mas afinidad
        pass

    

