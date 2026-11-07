# Import images generated in ChatGPT

1. Ask ChatGPT to create a mnemonic picture using the exact sound/object/meaning associations from Study.
2. Save the image locally as PNG. If the image is WEBP/JPEG, convert to PNG locally first.
3. Start Study; open or save a mnemonic scene; select the PNG file in the **Import image** control.
4. Imported PNG is validated using Pillow, limited to 8 MB and 4096 x 4096, and saved under `generated_media/<scene_id>.png`.
5. Existing image for that scene is replaced. Images are NOT stored in PostgreSQL or uploaded to GitHub. Back up the local `generated_media` folder and SQLite DB together.

Install the dependency: `py -m pip install -r requirements.txt`. Run tests: `py -m unittest discover -v`.

This does not connect ChatGPT conversations to the Windows server automatically. The optional cloud image API remains separate. No image is generated merely by importing a file.

Security: prototype is bound to loopback and has no login; do not expose port 8766 on the network. Future release requires per-user authorization, quotas, asset versioning and stronger provider controls.
