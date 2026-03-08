"""Quick scan script for batch import preview"""
import sys
sys.path.insert(0, r"C:\Users\windo\OneDrive\Desktop\Claude_Code\projects\merus-expert")

from batch.folder_scanner import FolderScanner

source_path = r"C:\4850 Law"
scanner = FolderScanner(source_path)
scanner.scan()
scanner.print_preview()
