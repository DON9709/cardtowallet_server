from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, Response
from starlette.responses import FileResponse as StarletteFileResponse
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
    print(f"[DEBUG] Incoming request to /generate-pass: brand_name={pass_data.brand_name}, member_number={pass_data.membership_number}")
    brand_styles = {
        "kt": {"backgroundColor": "rgb(0,0,0)", "foregroundColor": "rgb(255,255,255)"},
        "dalkomm": {"backgroundColor": "rgb(50,50,50)", "foregroundColor": "rgb(255,255,255)"},
        "starbucks": {"backgroundColor": "rgb(0,100,0)", "foregroundColor": "rgb(255,255,255)"},
        "cu": {"backgroundColor": "rgb(128,0,128)", "foregroundColor": "rgb(255,255,255)"},
        "l.point": {"backgroundColor": "rgb(255,255,255)", "foregroundColor": "rgb(0,0,0)"}
    }
    brand_map = {
        "스타벅스": "starbucks"
    }
    brand_key_raw = pass_data.brand_name.lower()
    brand_key = brand_map.get(brand_key_raw, brand_key_raw)
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
    brand_assets = os.path.join("assets", brand_key)
    print(f"[DEBUG] Looking for assets in: {brand_assets}")
    print(f"[DEBUG] Available files: {os.listdir(brand_assets) if os.path.exists(brand_assets) else 'Folder not found'}")
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
    try:
        subprocess.run([
            "openssl", "smime", "-binary", "-sign",
            "-certfile", "certs/pass.cer",
            "-signer", "certs/pass_certificate.pem",
            "-inkey", "certs/key.pem",
            "-in", f"{temp_dir}/manifest.json",
            "-out", f"{temp_dir}/signature",
            "-outform", "DER"
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Signature generation failed: {e}")

    print("[DEBUG] Files in temp_pass before zip:")
    for file in os.listdir(temp_dir):
        filepath = os.path.join(temp_dir, file)
        print(f" - {file}: {os.path.getsize(filepath)} bytes")

    # Step 5: Zip into .pkpass
    os.makedirs("output", exist_ok=True)
    pkpass_path = os.path.join("output", "membership.pkpass")
    with zipfile.ZipFile(pkpass_path, "w") as zf:
        for file in os.listdir(temp_dir):
            zf.write(os.path.join(temp_dir, file), arcname=file)
    # Debug: Print contents of generated .pkpass with error handling
    try:
        with zipfile.ZipFile(pkpass_path, "r") as zf:
            print("[DEBUG] Contents of generated .pkpass:")
            for name in zf.namelist():
                size = zf.getinfo(name).file_size
                print(f" - {name} ({size} bytes)")
    except zipfile.BadZipFile:
        print("[ERROR] Failed to open .pkpass: BadZipFile – the file may be corrupted or not a valid zip archive.")
    except Exception as e:
        print(f"[ERROR] Unexpected error while reading .pkpass: {e}")
    print(f"[DEBUG] PKPASS file created at: {pkpass_path}")
    print(f"[DEBUG] PKPASS file size: {os.path.getsize(pkpass_path)} bytes")

    file_response = StarletteFileResponse(pkpass_path, media_type="application/vnd.apple.pkpass")
    file_size = os.path.getsize(pkpass_path)
    file_response.headers["Content-Length"] = str(file_size)
    return file_response