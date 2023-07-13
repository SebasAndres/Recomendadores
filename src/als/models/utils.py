import pandas as pd
import requests

class uutils():

    def from_list_to_df(spark, list, column):    
        # Armo un dataframe columna a partir de una lista y el nombre de la columna    
        data = [{column: item} for item in list]
        return spark.createDataFrame(data)
