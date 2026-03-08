"""
Folder Scanner - Scan source folders for batch import
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from merus_expert.models.batch_import import CaseFolder, DryRunPreview

logger = logging.getLogger(__name__)


class FolderScanner:
    """
    Scans source folders to prepare for batch import.

    Features:
    - Parse folder names to extract client name and case number
    - Count files and calculate sizes
    - Generate dry-run previews
    - Validate folder structure
    """

    def __init__(self, source_path: str):
        """
        Initialize folder scanner.

        Args:
            source_path: Path to source folder (e.g., "C:\\4850 Law")
        """
        self.source_path = Path(source_path)
        if not self.source_path.exists():
            raise ValueError(f"Source path does not exist: {source_path}")
        if not self.source_path.is_dir():
            raise ValueError(f"Source path is not a directory: {source_path}")

        self._folders: List[CaseFolder] = []
        self._scanned = False

    def scan(self, include_empty: bool = False) -> List[CaseFolder]:
        """
        Scan source folder and return list of case folders.

        Args:
            include_empty: Include folders with no files

        Returns:
            List of CaseFolder objects
        """
        logger.info(f"Scanning source folder: {self.source_path}")

        self._folders = []
        for item in sorted(self.source_path.iterdir()):
            if item.is_dir():
                folder = CaseFolder.from_path(str(item))
                if folder.file_count > 0 or include_empty:
                    self._folders.append(folder)
                    logger.debug(f"Found folder: {folder.folder_name} ({folder.file_count} files)")

        self._scanned = True
        logger.info(f"Scan complete: {len(self._folders)} folders found")

        return self._folders

    @property
    def folders(self) -> List[CaseFolder]:
        """Get list of scanned folders"""
        if not self._scanned:
            self.scan()
        return self._folders

    @property
    def total_folders(self) -> int:
        """Get total number of folders"""
        return len(self.folders)

    @property
    def total_files(self) -> int:
        """Get total number of files across all folders"""
        return sum(f.file_count for f in self.folders)

    @property
    def total_size_bytes(self) -> int:
        """Get total size of all files in bytes"""
        return sum(f.total_size_bytes for f in self.folders)

    @property
    def total_size_mb(self) -> float:
        """Get total size in megabytes"""
        return self.total_size_bytes / (1024 * 1024)

    @property
    def total_size_gb(self) -> float:
        """Get total size in gigabytes"""
        return self.total_size_bytes / (1024 * 1024 * 1024)

    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of scanned folders.

        Returns:
            Dict with summary statistics
        """
        folders = self.folders
        if not folders:
            return {
                "source_path": str(self.source_path),
                "total_folders": 0,
                "total_files": 0,
                "total_size_mb": 0,
                "largest_folder": None,
                "smallest_folder": None,
            }

        sorted_by_files = sorted(folders, key=lambda f: f.file_count, reverse=True)

        return {
            "source_path": str(self.source_path),
            "total_folders": len(folders),
            "total_files": self.total_files,
            "total_size_mb": round(self.total_size_mb, 2),
            "total_size_gb": round(self.total_size_gb, 2),
            "largest_folder": {
                "name": sorted_by_files[0].folder_name,
                "file_count": sorted_by_files[0].file_count,
            },
            "smallest_folder": {
                "name": sorted_by_files[-1].folder_name,
                "file_count": sorted_by_files[-1].file_count,
            },
            "average_files_per_folder": round(self.total_files / len(folders), 1),
        }

    def generate_preview(
        self,
        case_type: str = "Workers' Compensation",
        include_case_number: bool = False
    ) -> DryRunPreview:
        """
        Generate a dry-run preview of what will be imported.

        Args:
            case_type: Case type to assign to all matters
            include_case_number: Include case number in matter name

        Returns:
            DryRunPreview object
        """
        job_id = f"preview_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        folders = self.folders

        matters = []
        warnings = []

        for folder in folders:
            matter_name = folder.get_matter_name(include_case_number)
            size_mb = folder.total_size_bytes / (1024 * 1024)

            matters.append({
                "name": matter_name,
                "folder": folder.folder_name,
                "file_count": folder.file_count,
                "total_size_mb": round(size_mb, 2),
            })

            # Add warnings for large folders
            if folder.file_count > 500:
                warnings.append(f"Large folder: {folder.folder_name} ({folder.file_count:,} files)")

            # Add warnings for very large files
            if size_mb > 100:
                warnings.append(f"Large folder size: {folder.folder_name} ({size_mb:.1f} MB)")

        # Estimate time: ~30 sec per file average
        estimated_hours = (self.total_files * 30) / 3600

        return DryRunPreview(
            job_id=job_id,
            source_path=str(self.source_path),
            case_type=case_type,
            include_case_number=include_case_number,
            matters_to_create=matters,
            total_matters=len(matters),
            total_files=self.total_files,
            total_size_mb=round(self.total_size_mb, 2),
            warnings=warnings,
            estimated_hours=round(estimated_hours, 1),
        )

    def print_preview(
        self,
        case_type: str = "Workers' Compensation",
        include_case_number: bool = False
    ):
        """
        Print a formatted preview to console.

        Args:
            case_type: Case type for all matters
            include_case_number: Include case number in names
        """
        preview = self.generate_preview(case_type, include_case_number)

        print(f"\n{'='*70}")
        print("BATCH IMPORT PREVIEW")
        print(f"{'='*70}\n")

        print(f"Source: {preview.source_path}")
        print(f"Case Type: {preview.case_type}")
        print(f"Include Case Number: {preview.include_case_number}")
        print()

        print(f"{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"  Total Matters to Create: {preview.total_matters}")
        print(f"  Total Files to Upload:   {preview.total_files:,}")
        print(f"  Total Size:              {preview.total_size_mb:,.1f} MB ({preview.total_size_mb/1024:.2f} GB)")
        print(f"  Estimated Time:          {preview.estimated_hours:.1f} hours")
        print()

        if preview.warnings:
            print(f"{'='*70}")
            print("WARNINGS")
            print(f"{'='*70}")
            for warning in preview.warnings:
                print(f"  ! {warning}")
            print()

        print(f"{'='*70}")
        print("MATTERS TO CREATE")
        print(f"{'='*70}")
        print(f"{'Matter Name':<40} {'Files':>8} {'Size (MB)':>12}")
        print(f"{'-'*40} {'-'*8} {'-'*12}")

        for matter in preview.matters_to_create:
            name = matter["name"][:38] + ".." if len(matter["name"]) > 40 else matter["name"]
            print(f"{name:<40} {matter['file_count']:>8,} {matter['total_size_mb']:>12.1f}")

        print(f"\n{'='*70}\n")

    def get_folders_by_file_count(self, descending: bool = True) -> List[CaseFolder]:
        """
        Get folders sorted by file count.

        Args:
            descending: Sort in descending order (largest first)

        Returns:
            Sorted list of CaseFolder objects
        """
        return sorted(self.folders, key=lambda f: f.file_count, reverse=descending)

    def get_folders_by_size(self, descending: bool = True) -> List[CaseFolder]:
        """
        Get folders sorted by total size.

        Args:
            descending: Sort in descending order (largest first)

        Returns:
            Sorted list of CaseFolder objects
        """
        return sorted(self.folders, key=lambda f: f.total_size_bytes, reverse=descending)

    def filter_by_file_count(self, min_files: int = 0, max_files: Optional[int] = None) -> List[CaseFolder]:
        """
        Filter folders by file count.

        Args:
            min_files: Minimum file count
            max_files: Maximum file count (None for no limit)

        Returns:
            Filtered list of CaseFolder objects
        """
        filtered = [f for f in self.folders if f.file_count >= min_files]
        if max_files is not None:
            filtered = [f for f in filtered if f.file_count <= max_files]
        return filtered


# === CLI Interface ===

def main():
    """CLI entry point for folder scanning"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python folder_scanner.py <source_path> [--preview]")
        print("Example: python folder_scanner.py 'C:\\4850 Law' --preview")
        sys.exit(1)

    source_path = sys.argv[1]
    show_preview = "--preview" in sys.argv

    try:
        scanner = FolderScanner(source_path)
        scanner.scan()

        summary = scanner.get_summary()
        print(f"\nSource: {summary['source_path']}")
        print(f"Folders: {summary['total_folders']}")
        print(f"Files: {summary['total_files']:,}")
        print(f"Size: {summary['total_size_mb']:,.1f} MB ({summary.get('total_size_gb', 0):.2f} GB)")

        if summary['largest_folder']:
            print(f"Largest: {summary['largest_folder']['name']} ({summary['largest_folder']['file_count']:,} files)")
        if summary['smallest_folder']:
            print(f"Smallest: {summary['smallest_folder']['name']} ({summary['smallest_folder']['file_count']:,} files)")

        if show_preview:
            print()
            scanner.print_preview(
                case_type="Workers' Compensation",
                include_case_number=False
            )

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
