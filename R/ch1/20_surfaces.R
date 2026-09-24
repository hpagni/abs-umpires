#!/usr/bin/env Rscript
# R/ch1/20_surfaces.R - Chapter 1 called-strike probability surfaces.
#
# ABSUMP_PLACEHOLDER. This is a stub. The owning W3 step writes the real
# script: mgcv::bam with s(plate_x_mid, plate_z_mid) by count and handedness,
# fit on the open window only, written to out/ch1/model/ with a provenance.json.
# The smooth is on the re-projected mid-plane pair, never on the raw plate_x and
# plate_z: Statcast reports those at the front of the plate through 2025 and at
# the middle from 2026, so a surface fit on the raw pair would read the plane
# change as a strike-zone change. plate_x_mid and plate_z_mid are on one plane
# for every season, and plane_source says how each row got there.
#
# The stub exists in phase 01 for one reason. GD-09, the red team, plants a
# held-out read in this file and requires tests/guard/test_no_sealed_reads.py
# to fail on it by file and line. A patch cannot apply to a file that is not
# there, so the file is here, minimal and honest, and the scan passes on it.
#
# Every read in this project goes through the open view. The held-out rows are
# not readable from here, in this phase or any later one, without the ceremony
# in SOP W9.7.

suppressPackageStartupMessages({
  library(arrow)
})

OPEN_VIEW <- "v_pitch_open"

surface_frame <- function(con) {
  # The one read. The open view is the only pitch source Chapter 1 has.
  # The real script filters by count and handedness here.
  DBI::dbGetQuery(con, paste("SELECT * FROM", OPEN_VIEW))
}

fit_surfaces <- function(con) {
  d <- surface_frame(con)
  message(nrow(d), " open pitches")
  stop("R/ch1/20_surfaces.R is a stub; the owning W3 step writes the fit.")
}

main <- function() {
  stop("R/ch1/20_surfaces.R is a stub; run it after the owning W3 step lands.")
}

if (identical(environment(), globalenv()) && !interactive()) {
  # Deliberately inert. The stub is never the thing that produces a number.
  invisible(NULL)
}
