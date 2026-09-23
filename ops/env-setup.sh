#!/bin/bash
# Base toolchain for the ABS project. Idempotent. Logs to env-setup.log.
set -u
log(){ echo "[$(date '+%H:%M:%S')] $*"; }
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:/opt/homebrew/bin:$PATH"

log "== uv =="
if ! command -v uv >/dev/null 2>&1; then curl -LsSf https://astral.sh/uv/install.sh | sh; fi
uv --version && uv python install 3.12 && uv python list | grep -E '3\.12' | head -2

log "== brew: jq, duckdb cli =="
brew install jq duckdb 2>&1 | tail -3

log "== R packages (user library) =="
Rscript -e '
dir.create(Sys.getenv("R_LIBS_USER"), recursive=TRUE, showWarnings=FALSE)
.libPaths(c(Sys.getenv("R_LIBS_USER"), .libPaths()))
options(repos=c(CRAN="https://cloud.r-project.org"), Ncpus=8)
need <- c("renv","testthat","arrow","duckdb","posterior","bayesplot","loo","brms","mgcv","gratia","baseballr","jsonlite","httr2","gt","shiny","bslib","implied")
miss <- setdiff(need, rownames(installed.packages()))
cat("installing:", paste(miss, collapse=", "), "\n")
if (length(miss)) install.packages(miss, type="binary")
install.packages("cmdstanr", repos=c("https://stan-dev.r-universe.dev", getOption("repos")))
cat("R_LIBS_USER:", Sys.getenv("R_LIBS_USER"), "\n")
print(sapply(c(need,"cmdstanr"), function(p) tryCatch(as.character(packageVersion(p)), error=function(e) "MISSING")))
' 2>&1 | tail -30

log "== CmdStan build (this is the untested step on macOS 26) =="
Rscript -e '
.libPaths(c(Sys.getenv("R_LIBS_USER"), .libPaths()))
library(cmdstanr)
cmdstanr::check_cmdstan_toolchain(fix=TRUE, quiet=FALSE)
cmdstanr::install_cmdstan(cores=8, overwrite=FALSE, quiet=FALSE)
cat("cmdstan version:", cmdstanr::cmdstan_version(), "\n")
f <- write_stan_file("data { int N; vector[N] y; } parameters { real mu; } model { y ~ normal(mu, 1); }")
m <- cmdstan_model(f); fit <- m$sample(data=list(N=5, y=c(1,2,3,4,5)), chains=2, iter_sampling=200, refresh=0)
print(fit$summary("mu"))
cat("SMOKE TEST OK\n")
' 2>&1 | tail -25

log "== done =="
