from typing import List

import sqlalchemy as sa


def merge_metadatas(*metas: sa.MetaData) -> sa.MetaData:
    result = sa.MetaData()

    for meta in metas:
        for table in meta.tables.values():
            table.to_metadata(result)
    
    return result
