from gui import app

if __name__ == '__main__':
    app.mainloop()

# To build the executable with PyInstaller, run this in a shell (not in Python):
#   python build.py                      # onedir  -> dist\Nova\Nova.exe  (fast startup, recommended)
#   python build.py --onefile            # onefile -> dist\Nova.exe       (single file, slower startup)
# Or directly:
#   pyinstaller --noconfirm --onedir --windowed --name Nova \
#     --collect-all customtkinter \
#     --exclude-module torch --exclude-module transformers --exclude-module librosa \
#     --add-data "assets;assets" \
#     main.py   