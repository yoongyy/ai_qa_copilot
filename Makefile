.PHONY: dev test demo backend frontend

dev:
	@echo "Starting backend (8000) and frontend (5173)..."
	@(cd backend && uvicorn app.main:app --reload --port 8000) & \
	 (cd frontend && npm run dev -- --host 0.0.0.0 --port 5173) & \
	 wait

test:
	@echo "Running Pytest API tests..."
	PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q backend/generated_tests/tests/api/test_vc_api.py
	@echo "Running Playwright UI tests..."
	cd frontend && npx playwright test ../backend/generated_tests/tests/ui/vc.spec.ts --config playwright.config.ts

demo:
	@echo "Demo instructions:"
	@echo "1) make dev"
	@echo "2) Open http://localhost:5173"
	@echo "3) Generate -> Run -> Propose Fix -> Apply -> Re-run"
