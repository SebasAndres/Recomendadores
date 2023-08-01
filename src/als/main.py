"""
Ejecucion del modelo
"""

from objects.als import byr_recommender
from argparse import ArgumentParser

from pyspark.sql import SparkSession

printf = lambda txt: print(f"\033[1;32;40m{txt}\033[0m")

if __name__ == "__main__":

    spark = SparkSession.builder.appName("session") \
                                .master("local[*]") \
                                .config("spark.cassandra.connection.host", "EL_HOST_VA_ACA") \
                                .config("com.datastax.spark", "spark-cassandra-connector_2.12:3.3.0")\
                                .getOrCreate()

    printf("-"*50)
    printf("RUNNING BYR_RECOMMENDER..")
    printf("-"*50)

    parser = ArgumentParser(description='Accion a realizar por el Recomendador')
    parser.add_argument('-a', '--action',
                        type=str,
                        default="help"
                        )    

    # Train
    parser.add_argument('-b', '--batch_size',
                        type=int,
                        help='# de registros a procesar por batch',
                        default=100
                        )
    parser.add_argument('-m', '--maxIter',
                        type=int,
                        help='# de iteraciones del ALS',
                        default=5)
    parser.add_argument('-r', '--rank',
                        type=int,
                        help='# de factores latentes',
                        default=50)
    parser.add_argument('-p', '--regParam',
                        type=float,
                        help='parametro de regularizacion',
                        default=0.01)

    # Recomendation
    parser.add_argument('-n', '--n',
                        type=int,
                        help='# de recomendaciones por usuario',
                        default=20)

    args = parser.parse_args()

    if args.action == "train":
        # Entrenamos el modelo con los ultimos batch_size datos de Cassandra
        Recommender = byr_recommender(spark)
        Recommender.train(batch_size=args.batch_size,
                          maxIter=args.maxIter,
                          rank=args.rank,
                          regParam=args.regParam)
    
    elif args.action == "user_recommendation":
        # Recomendamos para cada usuario y lo guardamos en elastic
        Recommender = byr_recommender(spark, load_last=True)
        Recommender.recommend_for_users(n=args.n)        

    elif args.action == "item_recommendation":
        # Recomendamos para cada item y lo guardamos en elastic
        Recommender = byr_recommender(spark, load_last=True)
        print(Recommender.model)
        Recommender.recommend_for_items(n=args.n)

    elif args.action == "update_rankings":
        # Cambiamos los rankings en el indice items de elasticsearch
        # con los ultimos batch_size datos de Cassandra 
        Recommender = byr_recommender(spark, load_last=True)
        Recommender.update_ranking_items(batch_size=args.batch_size)

    elif args.action == "top_popular":
        # Devuelve los contenidos mas populares
        Recommender = byr_recommender(spark, load_last=True)
        top_popular = Recommender.top_popular_v2(batch_size=10000, n=args.n)
        print(top_popular.show())

    elif args.action == "cold_start":
        pass

    else:
        printf("No se reconoce la accion {}".format(args.action))
        printf("Las acciones posibles son: train, user_recomendation, item_recomendation, update_rankings, top_popular, cold_start")
        
    printf("-"*50)

