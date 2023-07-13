
class Utils():

    def decode_interaction(interaction) -> tuple:
        # Dada una interaccion, devuelve la tripla (user_id, group_id, event_time)    
        d = interaction.asDict()
        return d["user_id"], d["group_id"], d["event_time"]