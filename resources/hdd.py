from flask_restful import Resource
from flask import request
from sqlalchemy.sql import func


from Model.Hdds import HddSchema, Hdd
from databases.db import db
from lib.logging import logging


class HddResource(Resource):
    def __init__(self):
        self.schema = HddSchema()
        self.schemaM = HddSchema(many=True)

    def _return(self, id):
        T = Hdd.query.where(Hdd.id == id).one()
        result = self.schema.dump(T)
        print(result)
        return result, 200

    def get(self, id=None):
        hdd = []
        statuscode = 200

        if id:
            hdd = Hdd.query.where(Hdd.id == id, Hdd.status != 2).all()
        else:
            hdd = Hdd.query.where(Hdd.status != 2).all()

        result = self.schemaM.dump(hdd)

        if hdd == []:
            statuscode = 404

        return result, statuscode

    def post(self, id=None):
        logging.info(request.get_json())
        if id != None:
            return "ID not expcted", 501
        payload = request.get_json()
        error = self.schema.validate(payload)
        if error:
            return error, 422

        hdd = Hdd(**self.schema.load(payload))
        db["session"].add(hdd)
        db["session"].flush()
        db["session"].refresh(hdd)

        db["session"].commit()

        return self._return(hdd.id)

    def delete(self, id):
        update_payload = dict(status=2, updatedAt=func.now())
        hdd = Hdd.query.where(Hdd.id == id).update(update_payload)
        db["session"].commit()
        logging.info(f"Output update: {hdd}")
        return {}, 200
