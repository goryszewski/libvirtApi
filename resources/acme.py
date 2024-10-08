from flask_restful import Resource
from flask import request, jsonify, Response, make_response
import base64, json
from lib.logging import logging
from lib.ca import sign_certificate_request, get_ca
from datetime import datetime, timedelta

from Model.AcmeAccount import (
    AccountModel,
    AccountProtectSchema,
    AccountPayloadSchema,
    RequestOrderSchema,
    OrderModel,
    AuthorizationModel,
    CertModel,
    ChallengeModel,
)


URL_SERVER = "http://10.17.3.1:8050/acme"
VALID_CRT_DAYS = 30


def decode_base64_fix(data):
    fix = "=" * int(len(data) % 4)
    payload = base64.b64decode(data + fix)
    return payload.decode()


def to_json(items):
    output = []
    for item in items:
        tmp = json.loads(item.to_json())
        if "_id" in tmp:
            del tmp["_id"]
        if "objectid" in tmp:
            del tmp["objectid"]
        output.append(tmp)
    return output


class Directory(Resource):
    def __init__(self):
        pass

    def get(self):
        output = {
            "newNonce": f"{URL_SERVER}/new-nonce",
            "newAccount": f"{URL_SERVER}/new-account",
            "newOrder": f"{URL_SERVER}/new-order",
            "revokeCert": f"{URL_SERVER}/revoke-cert",
            "keyChange": f"{URL_SERVER}/key-change",
        }
        return output, 200

    def post(sefl):
        return "", 501

    def put(self):
        return "", 501


class Account(Resource):
    def __init__(self):
        pass

    def post(self, id):
        headers = dict(request.headers)
        logging.debug(f" [Account] - headers : {headers}")

        account = AccountModel.objects(id=id).first()
        if account:
            output = {
                "status": account.status,
                "contact": account.contact,
                "termsOfServiceAgreed": account.termsOfServiceAgreed,
                "orders": f"{URL_SERVER}/account/{account.id}/orders",
            }
            response = make_response(jsonify(output), 200)
            return response
        else:
            output = {
                "type": "urn:ietf:params:acme:error:accountDoesNotExist",
                "detail": f"Account with ID {id} does not exist",
                "status": 404,
            }
            return output, 404


class NewAccount(Resource):
    def __init__(self):
        self.account_payload_schema = AccountPayloadSchema()
        self.account_protect_schema = AccountProtectSchema()

    def get(self):
        return "", 501

    def post(self):
        request_json = request.get_json()
        headers = dict(request.headers)
        logging.debug(f" [NewAccount] - headers : {headers}")

        protected = json.loads(decode_base64_fix(request_json["protected"]))
        logging.debug(f" [NewAccount] - protected : {protected}")

        error = self.account_protect_schema.validate(protected)
        if error:
            logging.error(f"1: {error}")
            return error, 422

        payload = json.loads(decode_base64_fix(request_json["payload"]))
        error = self.account_payload_schema.validate(payload)
        if error:
            logging.error(f"2: {error}")
            return error, 422

        logging.debug(f" [NewAccount] - payload : {payload}")

        account = AccountModel.objects(jwk=protected["jwk"]["n"]).first()

        rc = 501
        if account:
            rc = 200
        else:
            if "onlyReturnExisting" in payload and payload["onlyReturnExisting"]:
                output = {
                    "type": "urn:ietf:params:acme:error:accountDoesNotExist",
                    "detail": "No account exists with the provided key",
                    "status": 400,
                }
                return output, 400
            rc = 201
            account = AccountModel(
                **self.account_payload_schema.dump(payload), jwk=protected["jwk"]["n"]
            )
            account.save()

        output = {
            "contact": account.contact,
            "status": "valid",
            "orders": f"{URL_SERVER}/account/{account.id}/orders",
        }
        response = make_response(jsonify(output), rc)
        response.headers["Location"] = f"{URL_SERVER}/account/{account.id}"
        response.headers["Replay-Nonce"] = "6S8dQIvS7eL2ls4K2fB2sz-9I23cZJq_iBYjGn4Z7H8"
        return response

    def put(self):
        return "", 501


class AuthZ(Resource):
    def __init__(self):
        pass

    def get(self):
        return "", 501

    def post(sefl, id):
        authz = AuthorizationModel.objects(id=id).first()
        challenges_array = []
        authz_status = "valid"
        for challange_id in authz.challenges:
            challange = json.loads(
                ChallengeModel.objects(id=challange_id).first().to_json()
            )
            challenges_array.append(challange)
            if challange["status"] != "valid":
                authz_status = challange["status"]
        logging.info(f"[AuthZ] status - {authz.status} : {authz_status}")

        if authz.status != authz_status:
            authz.update(status=authz_status)
            authz.reload()

        output = {
            "status": authz.status,
            "expires": authz.expires,
            "identifier": authz.identifier,
            "challenges": challenges_array,
        }
        logging.debug(f"[AuthZ] output - {output}")

        response = make_response(jsonify(output), 200)
        response.headers["Location"] = f"{URL_SERVER}/authz/{id}"
        response.headers["Replay-Nonce"] = "6S8dQIvS7eL2ls4K2fB2sz-9I23cZJq_iBYjGn4Z7H8"
        return response


class Order(Resource):
    def __init__(self):
        pass

    def post(sefl, id):
        authorizations_array = []
        order_status = "ready"
        order = OrderModel.objects(id=id).first()
        authorizations = AuthorizationModel.objects(orderid=str(order.id))
        for athz in authorizations:
            authorizations_array.append(
                f"{URL_SERVER}/authz/{athz.id}",
            )
            if athz.status != "valid":
                order_status = "pending"
        logging.info(f"[Order] status - {order.status} : {order_status}")

        if order.status == "valid":
            pass
        elif order.status != order_status:
            order.update(status=order_status)
            order.reload()

        output = {
            "status": order.status,
            "certificate": "base64-encoded-certificate-data",
            "identifiers": to_json(order.identifiers),
            "authorizations": authorizations_array,
            "finalize": f"{URL_SERVER}/order/{order.id}/finalize",
            "certificate": f"{URL_SERVER}/certificate/{order.id}",
        }
        logging.debug(f"[Order] output - {output}")

        response = make_response(output, 200)
        response.headers["Location"] = f"{URL_SERVER}/order/{order.id}"
        response.headers["Replay-Nonce"] = "6S8dQIvS7eL2ls4K2fB2sz-9I23cZJq_iBYjGn4Z7H8"
        return response


class Challenge(Resource):
    def post(self, authz_id, type):
        # TODO external validator
        headers = dict(request.headers)
        logging.debug(f"[Challenge] - headers : {headers}")
        logging.debug(f"[Challenge] authz_id - {authz_id}")
        logging.debug(f"[Challenge] type - {type}")

        # authz = AuthorizationModel.objects(id=str(authz_id)).first()
        # authz.update(status="valid")

        challenge = ChallengeModel.objects(authzid=str(authz_id)).first()
        challenge.update(status="valid")

        # order = OrderModel.objects(id=authz.orderid)
        # order.update(status="ready")

        return {"status": "valid"}, 200


class NewOrder(Resource):
    def __init__(self):
        self.order_schema = RequestOrderSchema()

    def post(self):
        request_json = request.get_json()
        headers = dict(request.headers)
        logging.debug(f" [NewOrder] - headers : {headers}")

        protected = json.loads(decode_base64_fix(request_json["protected"]))
        logging.debug(f"[NewOrder] protected - {protected}")
        kid = protected["kid"]
        account_id = kid.split("/")[-1]
        logging.debug(f"[NewOrder] account_id - {account_id}")
        payload = json.loads(decode_base64_fix(request_json["payload"]))
        identifiers = sorted(
            payload["identifiers"], key=lambda x: (x["type"], x["value"])
        )
        logging.debug(f"[NewOrder] identifiers - {identifiers}")
        payload["identifiers"] = identifiers
        logging.debug(f"[NewOrder] payload - {payload}")

        error = self.order_schema.validate(payload)
        if error:
            logging.error(error)
            return error, 500
        current_time = datetime.utcnow()
        expires = current_time + timedelta(days=VALID_CRT_DAYS)

        rc = 501
        order = OrderModel.objects(**payload, accountid=account_id).first()
        if order:
            rc = 200
        else:
            order = OrderModel(
                **self.order_schema.dump(payload),
                status="pending",
                accountid=account_id,
                expires=expires.isoformat() + "Z",
            )
            order.save()
            rc = 201

        # create authorizations
        authz_array = []
        identifiers = to_json(order.identifiers)
        for identifier in identifiers:
            authz = AuthorizationModel(
                accountid=account_id,
                orderid=str(order.id),
                status="pending",
                expires=expires.isoformat() + "Z",
                identifier=identifier,
                challenges=[],
                wildcard=False,
            )
            authz.save()
            challenge = ChallengeModel(
                url=f"{URL_SERVER}/challenge/{authz.id}/http-01",
                type="http-01",
                status="pending",
                token="def456",
                validation="dns-txt-record-value",
                authzid=str(authz.id),
            )
            challenge.save()

            challenges = [str(challenge.id)]

            authz.update(challenges=challenges)
            authz.reload()
            authz_array.append(f"{URL_SERVER}/authz/{authz.id}")

        output = {
            "status": order.status,
            "expires": order.expires,
            "identifiers": to_json(order.identifiers),
            "authorizations": authz_array,
            "finalize": f"{URL_SERVER}/order/{order.id}/finalize",
        }
        logging.debug(f"[NewOrder] output - {output}")

        response = make_response(jsonify(output), rc)
        response.headers["Location"] = f"{URL_SERVER}/order/{order.id}"
        response.headers["Replay-Nonce"] = "6S8dQIvS7eL2ls4K2fB2sz-9I23cZJq_iBYjGn4Z7H8"
        return response


class NewNonce(Resource):
    def __init__(self):
        pass

    def head(self):
        response = Response()
        response.headers["Replay-Nonce"] = "6S8dQIvS7eL2ls4K2fB2sz-9I23cZJq_iBYjGn4Z7H8"
        return response

    def get(self):
        return "", 501

    def post(sefl):
        return "", 501

    def put(self):
        return "", 501


class AcmeChallenge(Resource):
    def __init__(self):
        pass

    def get(self):
        return "", 501

    def post(sefl):
        return "", 501

    def put(self):
        return "", 501


class FinalizeOrder(Resource):
    def __init__(self):
        pass

    def get(self):
        return "", 501

    def post(sefl, id):
        request_json = request.get_json()

        protected = decode_base64_fix(request_json["protected"])
        logging.debug(f"[FinalizeOrder] protected - {protected}")

        payload = json.loads(decode_base64_fix(request_json["payload"]))
        logging.debug(f"[FinalizeOrder] payload - {payload}")
        authorizations_array = []

        test = sign_certificate_request(payload["csr"])

        order = OrderModel.objects(id=id).first()
        logging.info(f"[Order] status - {order.status} : valid")
        order.update(status="valid")
        order.reload()
        authorizations = AuthorizationModel.objects(orderid=str(order.id))

        crt = CertModel(orderid=str(order.id), cert=test)
        crt.save()

        for athz in authorizations:
            authorizations_array.append(
                f"{URL_SERVER}/authz/{athz.id}",
            )
        output = {
            "status": "valid",
            "certificate": "base64-encoded-certificate-data",
            "identifiers": to_json(order.identifiers),
            "authorizations": authorizations_array,
            "finalize": f"{URL_SERVER}/order/{order.id}/finalize",
            "certificate": f"{URL_SERVER}/certificate/{order.id}",
        }
        response = make_response(jsonify(output), 200)
        response.headers["Replay-Nonce"] = "6S8dQIvS7eL2ls4K2fB2sz-9I23cZJq_iBYjGn4Z7H8"
        return response


class Certs(Resource):
    def __init__(self):
        pass

    def post(self, id):
        rc = 404

        output = ""
        # TODO add chain
        cert_data = CertModel.objects(orderid=str(id)).first()
        if cert_data:
            rc = 200
            output = f"{cert_data.cert}\n{get_ca().decode()}"
            # output = f"{cert_data.cert}"
            logging.info(output)

        response = make_response(output, rc)
        response.mimetype = "application/pem-certificate-chain"
        return response


class Finalize(Resource):
    def __init__(self):
        pass

    def get(self):
        return "", 501

    def post(sefl, order_id):
        # Zwrócenie odpowiedzi z certyfikatem
        return {}, 501

    def put(self):
        return "", 501


class RevokeCert(Resource):
    def __init__(self):
        pass

    def get(self):
        return "", 501

    def post(sefl):
        return "", 501

    def put(self):
        return "", 501
