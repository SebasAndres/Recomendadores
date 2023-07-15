import requests
import pandas as pd

class Interpreter():

    def __init__(self, elastic_metadata):
        self.elastic_metadata = elastic_metadata #
        pass

    def describirItem(self, group_id:int) -> tuple:
        # Dado un group_id,
        # Describe que sus caracteristicas principales
        
        url = f"{self.elastic_metadata}/grupo/{group_id}? \
            _source=NOMBRE_PROVEEDOR,NOMBRE_ESP,TITULO_ESP,DESCRIPCION_ESP,INFO_GENERO"        
        resp = requests.get(url).json()

        try:
            proveedor = resp["_source"]["NOMBRE_PROVEEDOR"]
            nombre = resp["_source"]["TITULO_ESP"]
            genero = resp["_source"]["INFO_GENERO"][0]["GENERO_ESP"]
            descripcion = resp["_source"]["DESCRIPCION_ESP"]
            return group_id, nombre, genero, proveedor, descripcion
        except IndexError:
            return None


    def interpretar_recomendaciones(self, group_id:int, recommendations:list) -> pd.DataFrame: 
        # Funcion para interpretar las recomendaciones dadas

        print(f"Item base:")
        print(self.describirItem(group_id))
        
        recs:list = []
        ignored:int = 0

        for g_id, score in recommendations:    
            values = self.describirItem(g_id)
            if values:
                recs.append(values)
            else:
                ignored += 1

        descr = pd.DataFrame(recs, columns=["id", "nombre", "genero", "proveedor", "descripcion"])
    
        return ignored, descr