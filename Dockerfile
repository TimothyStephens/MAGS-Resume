FROM mambaorg/micromamba:1.5.8

LABEL author="Timothy Stephens"
LABEL version="1.0"
LABEL description="Docker container for MAGS-Resume Studio"

USER root
RUN mkdir -p /opt/MAGS-Resume && chown $MAMBA_USER:$MAMBA_USER /opt/MAGS-Resume
USER $MAMBA_USER

WORKDIR /opt/MAGS-Resume

# Copy environment file and create the conda environment
COPY --chown=$MAMBA_USER:$MAMBA_USER environment.yml /opt/environment.yml
RUN micromamba create -y -n mags-resume -f /opt/environment.yml && \
    micromamba clean --all --yes

# Configure environment variables to use the created environment
ENV PATH="/opt/conda/envs/mags-resume/bin:$PATH"
ENV PYTHONPATH="/opt/MAGS-Resume:$PYTHONPATH"
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# Copy the rest of the application code
COPY --chown=$MAMBA_USER:$MAMBA_USER . /opt/MAGS-Resume

# Install the package if installer exists
RUN if [ -f pyproject.toml ] || [ -f setup.py ]; then \
        pip install --no-cache-dir . ; \
    else \
        echo "No setup.py or pyproject.toml found. Project will be added to PYTHONPATH." ; \
    fi

ENTRYPOINT ["mags-resume"]
CMD ["studio"]