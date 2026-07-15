import argparse
import sys
import logging
import config

# Initialize logger
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# Ultility selection

def main():
    parser = argparse.ArgumentParser(
        description="Anki Toolkit: Analytics and Automated Tagging Systems"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available utilities")
    subparsers.add_parser("tag-mesh", help="Run MeSH API auto-tagging.")
    subparsers.add_parser("tag-stats", help="Tag cards automatically using review metrics (speed & difficulty).")
    subparsers.add_parser("export-report", help="Compile daily retention data metrics as an .md file.")
    
    args = parser.parse_args()
    
    if args.command == "tag-mesh":
        from src.modules.mesh_tagger import main as mesh_main
        mesh_main()
    elif args.command == "tag-stats":
        from src.modules.performance import main as perf_main
        perf_main()
    elif args.command == "export-report":
        from src.modules.report import main as report_main
        report_main()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
