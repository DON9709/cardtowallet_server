from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
import json, os, hashlib, subprocess, zipfile

app = FastAPI()

class PassData(BaseModel):
    name: str
    membership_number: str
    brand_name: str
    expiration_date: str | None

@app.post("/generate-pass")
async def generate_pass(pass_data: PassData):
    brand_styles = {
        "kt": {"backgroundColor": "rgb(0,0,0)", "foregroundColor": "rgb(255,255,255)"},
        "dalkomm": {"backgroundColor": "rgb(50,50,50)", "foregroundColor": "rgb(255,255,255)"},
        "starbucks": {"backgroundColor": "rgb(0,100,0)", "foregroundColor": "rgb(255,255,255)"},
        "cu": {"backgroundColor": "rgb(128,0,128)", "foregroundColor": "rgb(255,255,255)"},
        "l.point": {"backgroundColor": "rgb(255,255,255)", "foregroundColor": "rgb(0,0,0)"}
    }
    brand_key = pass_data.brand_name.lower()
    style = brand_styles.get(brand_key, {"backgroundColor": "rgb(255,255,255)", "foregroundColor": "rgb(0,0,0)"})

    temp_dir = "temp_pass"
    os.makedirs(temp_dir, exist_ok=True)

    # Step 1: Create pass.json
    pass_json = {
        "formatVersion": 1,
        "passTypeIdentifier": "pass.com.DonLee.CardtoWallet",
        "serialNumber": pass_data.membership_number,
        "teamIdentifier": "2W9KP2B6Y9",  # Replace with your Apple Team ID
        "organizationName": pass_data.name,
        "description": f"{pass_data.name}'s Membership Card",
        "logoText": pass_data.brand_name,
        "backgroundColor": style["backgroundColor"],
        "foregroundColor": style["foregroundColor"],
        "generic": {
            "primaryFields": [
                {
                    "key": "member",
                    "label": "회원 이름",
                    "value": pass_data.name
                },
                {
                    "key": "number",
                    "label": "멤버십 번호",
                    "value": pass_data.membership_number
                }
            ]
        }
    }
    if pass_data.expiration_date:
        pass_json["expirationDate"] = pass_data.expiration_date

    with open(f"{temp_dir}/pass.json", "w") as f:
        json.dump(pass_json, f, indent=4, ensure_ascii=False)

    # Step 2: Copy icon and logo
    brand_assets = os.path.join("assets", pass_data.brand_name)
    for file in ["icon.png", "logo.png"]:
        src = os.path.join(brand_assets, file)
        if os.path.exists(src):
            with open(src, "rb") as fsrc, open(f"{temp_dir}/{file}", "wb") as fdst:
                fdst.write(fsrc.read())

    # Step 3: Create manifest.json
    manifest = {}
    for filename in os.listdir(temp_dir):
        filepath = os.path.join(temp_dir, filename)
        with open(filepath, "rb") as f:
            sha1 = hashlib.sha1(f.read()).hexdigest()
            manifest[filename] = sha1

    with open(f"{temp_dir}/manifest.json", "w") as f:
        json.dump(manifest, f, indent=4)

    # Step 4: Sign manifest
    subprocess.run([
        "openssl", "smime", "-binary", "-sign",
        "-certfile", "certs/pass.cer",
        "-signer", "certs/pass_certificate.pem",
        "-inkey", "certs/key.pem",
        "-in", f"{temp_dir}/manifest.json",
        "-out", f"{temp_dir}/signature",
        "-outform", "DER"
    ], check=True)

    # Step 5: Zip into .pkpass
    os.makedirs("output", exist_ok=True)
    pkpass_path = os.path.join("output", "membership.pkpass")
    with zipfile.ZipFile(pkpass_path, "w") as zf:
        for file in os.listdir(temp_dir):
            zf.write(os.path.join(temp_dir, file), arcname=file)

    return FileResponse(pkpass_path, media_type="application/vnd.apple.pkpass")