#!/bin/bash
cd "/Users/user/Downloads/00. 클로드/beauty-trend-dashboard"
exec python3 -m streamlit run dashboard.py --server.port 8502 --server.headless true
