import pandas as pd
import requests

class uutils():

    def from_list_to_df(spark, list, column):    
        # Armo un dataframe columna a partir de una lista y el nombre de la columna    
        data = [{column: item} for item in list]
        return spark.createDataFrame(data)

    def decode_interaction(interaction) -> tuple:
        # Dada una interaccion, devuelve la tripla (user_id, group_id, event_time)    
        d = interaction.asDict()
        return d["user_id"], d["group_id"], d["event_time"]
