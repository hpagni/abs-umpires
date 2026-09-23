# .Rprofile - R startup for abs-umpires. SOP W1.5.
# Loaded by every R session whose working directory is the repository root.
# Order matters: the DYLD guard runs before anything else, options are set before
# renv activates so that renv installs from the pinned repositories.

# A non-empty DYLD_LIBRARY_PATH makes the CmdStan toolchain link against the wrong
# libraries on macOS. SOP W1.5 and gate RP-04 require it to be empty. Hard stop.
if (nzchar(Sys.getenv("DYLD_LIBRARY_PATH"))) {
  stop(
    "DYLD_LIBRARY_PATH is non-empty: '", Sys.getenv("DYLD_LIBRARY_PATH"), "'. ",
    "Unset it and start R again. CmdStan does not build correctly with it set.",
    call. = FALSE
  )
}

options(
  repos = c(
    CRAN = "https://cloud.r-project.org",
    stan = "https://stan-dev.r-universe.dev"
  ),
  Ncpus = 8,
  warn = 1
)

# CmdStan lives outside the R library. A later R upgrade needs only the cmdstanr
# package reinstalled; the CmdStan build at this path is untouched. SOP W1.5.
Sys.setenv(CMDSTAN = path.expand("~/.cmdstan/cmdstan-2.40.0"))

source("renv/activate.R")
