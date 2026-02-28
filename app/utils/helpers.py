from bson import ObjectId


def str_to_objectid(id_str: str) -> ObjectId:
    if not ObjectId.is_valid(id_str):
        raise ValueError(f"Invalid ObjectId: {id_str}")
    return ObjectId(id_str)


def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB doc _id to string."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc