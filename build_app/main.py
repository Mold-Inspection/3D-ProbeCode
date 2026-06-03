from geometry_engine10 import MoldGeometry
# Old Manager
# from ui_manager import UIManager
from customTkinter_ui_manager import UIManager

def main():
    print("Starting App...")
    
    # 1. Create an empty math engine (no file loaded yet)
    geo = MoldGeometry()
    
    # 2. Pass it to the UI
    ui = UIManager(geo)
    # 3. Show the UI!
    ui.show()

if __name__ == "__main__":
    main()