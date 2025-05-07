from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
import json
import os
import shutil
import subprocess
from uuid import uuid4

app = FastAPI()

@app.get("/")
def root():
    return {"message": "CardtoWallet backend is running!"}

@app.post("/generate-pass")
async def generate_pass(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"error": "Invalid JSON in request body"}
    name = data.get("name", "Unknown")
    number = data.get("membership_number", "0000000000")

    pass_id = str(uuid4())
    folder = f"passes/{pass_id}"
    os.makedirs(folder, exist_ok=True)

    pass_json = {
        "formatVersion": 1,
        "passTypeIdentifier": "pass.com.example.cardtowallet",
        "serialNumber": pass_id,
        "teamIdentifier": "YOUR_TEAM_ID",
        "organizationName": "CardtoWallet",
        "description": "CardtoWallet Membership Card",
        "foregroundColor": "rgb(255, 255, 255)",
        "backgroundColor": "rgb(0, 122, 255)",
        "barcode": {
            "message": number,
            "format": "PKBarcodeFormatQR",
            "messageEncoding": "iso-8859-1"
        },
        "generic": {
            "primaryFields": [
                {"key": "name", "label": "Name", "value": name}
            ],
            "secondaryFields": [
                {"key": "id", "label": "Membership No.", "value": number}
            ]
        }
    }

    with open(os.path.join(folder, "pass.json"), "w") as f:
        json.dump(pass_json, f, indent=4)

    for filename in ["icon.png", "icon@2x.png", "icon@3x.png", "logo.png"]:
        source_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "static", filename))
        dest_path = os.path.join(folder, filename)
        if not os.path.exists(source_path):
            return {"error": f"Missing required image file: {filename}"}
        shutil.copy(source_path, dest_path)

    manifest_path = f"{folder}/manifest.json"
    manifest = {}
    for filename in os.listdir(folder):
        filepath = os.path.join(folder, filename)
        result = subprocess.run(["shasum", "-a", "1", filepath], capture_output=True, text=True)
        manifest[filename] = result.stdout.split()[0]

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)

    signature_path = f"{folder}/signature"
    subprocess.run([
        "openssl", "smime", "-binary", "-sign",
        "-certfile", "certs/pass-2.cer",
        "-signer", "certs/pass_certificate.pem",
        "-inkey", "certs/private_key.pem",
        "-in", manifest_path,
        "-out", signature_path,
        "-outform", "DER"
    ])

    pkpass_path = f"{folder}.pkpass"
    shutil.make_archive(pkpass_path.replace(".pkpass", ""), 'zip', folder)
    os.rename(pkpass_path.replace(".pkpass", "") + ".zip", pkpass_path)

    return FileResponse(pkpass_path, media_type="application/vnd.apple.pkpass", filename="cardtowallet.pkpass")