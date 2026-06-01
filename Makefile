build-WebhookFunction:
	python -m pip install --upgrade pip
	python -m pip install -r infra/webhook-requirements.txt -t "$(ARTIFACTS_DIR)"
	cp -R src "$(ARTIFACTS_DIR)/src"
