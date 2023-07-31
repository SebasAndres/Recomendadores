"""
Clase con el nuevo modelo de recomendador 
BYR_RECOMMENDER
"""

from pyspark.ml.recommendation import ALS, ALSModel
from pyspark.sql.functions import col, lit, udf
from pyspark.sql import DataFrame
from pyspark.sql.types import *
from tqdm import tqdm
import datetime
import os

printf = lambda txt: print(f"\033[1;32;40m{txt}\033[0m")

class byr_recommender():
    
    def __init__(self, spark, load_last=False, maxIter=5, rank=50, regParam=0.01):
        self.spark = spark
        
        if load_last:            
            available_models = os.listdir("models/")
            model_date = [(model, os.path.getctime("models/{}".format(model))) for model in available_models]

            if len(available_models) == 0:
                raise Exception("No hay modelos entrenados")
            
            # time_j > time_i <=> model_j mas reciente que model_i
            last_model = sorted(model_date, key=lambda x: x[1], reverse=True)[0][0]
            last_url = "models/{}".format(last_model)

            self.model = ALSModel.load(last_url)
        
        pass
    
    def train(self, batch_size:int, maxIter:int, rank:int, regParam:float):
        """ 
        MINI_BATCH
        Entrena al modelo leyendo los datos de cassandra y 
        actualiza el ranking de los items mas vistos.

        Parametros:
            * batch_size: # de registros a leer de cassandra
            * maxIter: # de iteraciones del ALS
            * rank: # de factores latentes
            * regParam: parametro de regularizacion
        """

        self.als = ALS(maxIter=maxIter,
                       rank=rank,
                       regParam=regParam,
                       userCol='user_id',
                       itemCol='group_id',
                       ratingCol='view',
                       implicitPrefs=True
                      )

        # Leo los datos de Cassandra        
        load_options = {"table": "TABLE", "keyspace": "KEYSPACE"}        
        df = self.spark.read.format("org.apache.spark.sql.cassandra").options(**load_options).load()        
        df = df.orderBy(col("event_time").desc())
        df = df.limit(batch_size)

        train = df.withColumn("view", lit(1))

        # Entreno el modelo
        self.model = self.als.fit(train)

        # Guardo el modelo
        version_date = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.model.save("models/als_vers_{}".format(version_date))

    def recommend_for_users(self, n:int):
        """ 
        Recomendacion por usuario: 
        Arma las recomendaciones por usuario con el ALSModel y las agrega como nodo
        a cada usuario en el indice correspondiente de elasticsearch (users).

        Parametros:
            * n: # de recomendaciones
        """
        
        # Armo las recomendaciones
        recommendations =  self.model.recommendForAllUsers(n)
        
        # Agrego las recomendaciones a elasticsearch
        recommendations_list = recommendations.collect()
        pbar = tqdm(total=len(recommendations_list))

        for recm in recommendations_list:
            # add to elastic -> 
            # elastic[index][user_id]["recommendations"] = recm
            print(recm.group_id, recm.rating)
            pbar.update(1)

        pbar.close()

    def recommend_for_items(self, n:int):
        """
        Recomendacion por items: 

        Arma las recomendaciones por item con el ALSModel y las agrega como nodo
        a cada item en el indice correspondiente de elasticsearch (items).

        Solo recomienda para los items que fueron entrenados en el ultimo modelo cargado.
        
        Parametros:
            * n: # de recomendaciones
        """
        
        # A cada item le busco items similares
        if self.model is None:
            raise Exception("No hay modelo entrenado")

        items = self.model.itemFactors.select("id").collect()
        pbar = tqdm(total=len(items))

        for item in items:
            similar_items = self.als_similar_items(item.id, n)            
            # add to elastic -> 
            # elastic[index][item_id]["similar_items"] = similar_items
            pbar.update(1)
            pass

        pbar.close()
        
    def als_similar_items(self, item_id:int, n) -> DataFrame:
        """ 
        Recomendacion por item: devuelve los n items similares a item_id 
        Parametros:
            * item_id: id del item
            * n: # de recomendaciones
        """

        # Factores latentes del item
        y_i = self.model.itemFactors.filter(self.model.itemFactors.id == item_id) \
                                    .select("features").collect()[0][0]

        # Armo una columna con las diferencias entre los factores de cada item y los del item dado 
        differencer = udf(lambda x: sum([(list(x)[k]-y_i[k])**2 for k in range(len(list(x)))]), FloatType())
        distances = self.model.itemFactors.withColumn('difference', differencer('features'))
        
        return distances.orderBy(col('difference')).limit(n+1)

    def update_ranking_items(self, batch_size):
        """
        Actualiza el ranking de los mas vistos en el indice de elasticsearch (items)
        """

        # Leo los datos de Cassandra        
        load_options = {"table": "view_events", "keyspace": "clarovideo"}        
        df = self.spark.read.format("org.apache.spark.sql.cassandra").options(**load_options).load()        
        df = df.orderBy(col("timestamp").desc())
        df = df.limit(batch_size)
                
        # Agrego los rankings en un DataFrame
        # Obs: Ranking(item_j) = unique_counts.indexOf(counts(item_j)) + 1
        items_counts = df.groupBy(df.group_id).count()
        unique_counts = set([i['count'] for i in items_counts.collect()])
        unique_counts = list(unique_counts)

        rankingFromCount = lambda count, unique_counts: unique_counts.index(count) + 1
        udfRankings = udf(rankingFromCount, IntegerType())

        # item_id | count | ranking
        rankings =  items_counts.withColumn("ranking", udfRankings('count', lit(unique_counts)))

        # Agrego los rankings en elasticsearch 
        ranking_list = rankings.collect()
        pbar = tqdm(total=len(ranking_list))

        for item_id, rank in ranking_list:
            printf(f"item_id: {item_id}, rank: {rank}")
            # add to elastic -> 
            # elastic[index][item_id]["rank"] = rank
            pbar.update(1)

        pbar.close()

    def top_popular_v1(self, n:int):
        """ 
        Recomendacion por Popularidad: devuelve los n grupos mas populares 
        buscando en el indice de elasticsearch (items) con el nodo rank.
        Parametros:
            * n: # de recomendaciones
        """
        query = """ get from elastic search top n items, based on node ranking"""
        return -1

    def top_popular_v2(self, batch_size:int, n:int):
        """ 
        Recomendacion por Popularidad: devuelve los n grupos mas populares 
        armando un counts a partir del dataset de Cassandra.
        Parametros:
            * batch_size: # de registros a leer de cassandra
            * n: # de recomendaciones
        """

        # Leo los datos de Cassandra        
        load_options = {"table": "view_events", "keyspace": "clarovideo"}        
        df = self.spark.read.format("org.apache.spark.sql.cassandra").options(**load_options).load()        
        df = df.orderBy(col("event_time").desc())
        df = df.limit(batch_size)

        # Ordeno por counts
        items_counts = df.groupBy(df.group_id).count().orderBy(col("count").desc())
        
        return items_counts.limit(n) # es un df

    def cold_start(self, n) -> DataFrame:
        return self.top_popularity(n)
