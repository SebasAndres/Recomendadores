import requests

## IDEA DEL ELASTIC_RECOMMENDATIONS

# indice items: { item_id: {index: 0, viewers: [user_id, ---, user_id]}, similar_items: [item_id_0, ..., item_id_10] }
# indice usuarios: { user_id: index }

class ElasticHelper():

    def __init__(self, es_recommendations, es_metadata):
        self.es_recommendations = es_recommendations # aun no existe      
        self.es_metadata = es_metadata #  

    def get_item_metadata(self, itemid):        
        # Dado un group id, devuelve la metadata necesaria para filtrar y potenciar contenido
        item_metadata:dict = dict() 
        url = f"{self.es_host}/metadata/_doc/{itemid}"
        try:
            resp:dict = requests.get(url=url).json()
            if not resp['found']:
                # print(group_id, "not found")
                # mandar a popular
                pass
            else:
                filtros:list = resp["_source"]["infoFiltros"] 
                item_metadata.update({"filtros": filtros})   
        except Exception:
            print("No se pudo acceder al indice")
    
        return item_metadata
    
    def n_items_in_recommendation(self):
        # Devuelve la cantidad de items en el indice de recomendaciones
        return 100

    def n_users_in_recommendation(self):
        # Devuelve la cantidad de usuarios en el indice de recomendaciones
        return 100

    def update_item_viewers(self, dataset):
        # Dado un dataset,
        # actualiza el indice recomendation con las views no registradas    
        return dict()
    
    def get_item_index(self, item_id, index=False):
        # Dado un item_id, devuelve el indice del item en el es_recommendation
        # si index = True, me pasa como parametro el indice del usuario en el elastic
        # si index = False, me pasa como parametro el group_id
        pass

    def get_item_viewers(self, item_id):
        # Dado un item_id, devuelve los viewers del item en el es_recommendation
        pass
    
    def add_user(self, user_id, index):
        # Agrego el usuario el indice de recomendaciones
        pass

    def add_item(self, item_id, index):
        # Agrego al item al indice de recomendaciones
        pass

    def is_valid_group_id(self, group_id) -> bool:
        # group_id esta en es_recommendation?
        return False 
    
    def is_valid_user_id(self, user_id) -> bool:
        # user_id esta en es_recommendation?
        return False