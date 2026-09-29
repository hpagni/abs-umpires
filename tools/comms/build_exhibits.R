# tools/comms/build_exhibits.R -- SOP W6.10. Table 1 and Figure 1 of the SSAC abstract.
#
# Both exhibits are drawn from the same ledger as the text, docs/numbers.json, from the
# table1 cells T1_<ROW>_<COL> that tools/comms/export_numbers.R carries from W3.16's
# T4_decomposition.csv and W3.17's T4_plane_component.csv. Printed strings come from the
# ledger as the exporter rounded them, so the number gate traces every cell.
#
# Outputs, each with its sidecar:
#   abstract/table1.md          the table, for review and for the paste sheet
#   abstract/table1.png         the same table as an image, for an upload field
#   abstract/table1.inline.md   the edges in plain text, for a form with no upload field
#   out/tables/table1_data.csv  the sidecar: one row per cell, value and printed strings
#   abstract/figure1.png        dot-and-interval small multiples, one panel per quantity,
#                               8 cm wide and grayscale (SOP W6.10: legible at 8 cm)
#   abstract/figure1.alt.txt    alt text, at least 40 characters (WR-14)
#   out/tables/figure1_data.csv the sidecar: the rows the figure plots
#
# SSAC allows two tables or figures combined. These are the two. The figure is rung 1 of
# the cut ladder; the owner decides at review R1 whether it stays.
#
#   Rscript tools/comms/build_exhibits.R [--ledger F] [--tag T] [--abstract-dir D]
#                                        [--tables-dir D]
#
# --tag T inserts ".T" before every output extension (the dry run passes SYNTHETIC).
# Exit 0 built; 1 the ledger holds no table1 cell; 2 usage.

suppressPackageStartupMessages({
  library(jsonlite)
  library(ggplot2)
})

script_dir <- function() {
  a <- grep("^--file=", commandArgs(FALSE), value = TRUE)
  normalizePath(dirname(sub("^--file=", "", a[1])))
}
ROOT <- normalizePath(file.path(script_dir(), "..", ".."))
opt <- function(args, name, default = NULL) {
  i <- match(name, args)
  if (is.na(i)) default else args[i + 1]
}
rp <- function(p) if (grepl("^/", p)) p else file.path(ROOT, p)
tagged <- function(dir, name, tag) {
  if (!nzchar(tag)) return(file.path(dir, name))
  m <- regmatches(name, regexec("^([^.]+)(\\..*)$", name))[[1]]
  file.path(dir, paste0(m[2], ".", tag, m[3]))
}

cells_from_ledger <- function(ledger, spec) {
  by_slot <- list()
  for (e in ledger$entries) if (!is.null(e$slot)) by_slot[[e$slot]] <- e
  rows <- list()
  for (r in spec$table1$rows) for (c in spec$table1$cols) {
    slot <- paste0("T1_", r[[1]], "_", c[[1]])
    e <- by_slot[[slot]]
    rows[[length(rows) + 1]] <- data.frame(
      row = r[[1]], row_label = r[[2]], col = c[[1]], col_label = c[[2]], units = c[[3]],
      slot = slot,
      point = if (is.null(e)) NA_real_ else as.numeric(e$value),
      lo95 = if (is.null(e$lo95)) NA_real_ else as.numeric(e$lo95),
      hi95 = if (is.null(e$hi95)) NA_real_ else as.numeric(e$hi95),
      print_point = if (is.null(e)) NA_character_ else e$print$point,
      print_lo95 = if (is.null(e$print$lo95)) NA_character_ else e$print$lo95,
      print_hi95 = if (is.null(e$print$hi95)) NA_character_ else e$print$hi95,
      source = if (is.null(e)) NA_character_ else e$source,
      stringsAsFactors = FALSE
    )
  }
  do.call(rbind, rows)
}

cell_text <- function(d) {
  ifelse(is.na(d$print_point), "n/a",
         ifelse(is.na(d$print_lo95), d$print_point,
                paste0(d$print_point, " [", d$print_lo95, ", ", d$print_hi95, "]")))
}

# The interval method is the Chapter 1 pre-registration's, docs/prereg/ch1.md: 1,000
# draws from N(beta, Vc), mgcv's covariance corrected for smoothing-parameter
# uncertainty. The standardisation is the same file's: the 2024 mix of count class and
# batter side, read for a 72-inch batter.
CAPTION <- paste(
  "Table 1. Change in the 50 percent contour by component, for a 72-inch batter at the",
  "2024 mix of count and batter side. Each cell is a point estimate [95% interval] from",
  "1,000 coefficient draws that include smoothing-parameter uncertainty. A positive value",
  "moves an edge up or outward, or enlarges the area."
)

# Short row names for the figure, which is read at 8 cm.
FIG_ROWS <- c(PRE = "Pre-trend, per season", BUF = "Buffer, 2025", ABS = "Challenges, 2026",
              PLANE = "Plate plane, 2025")

main <- function(args) {
  ledger_path <- rp(opt(args, "--ledger", "docs/numbers.json"))
  tag <- opt(args, "--tag", "")
  adir <- rp(opt(args, "--abstract-dir", "abstract"))
  tdir <- rp(opt(args, "--tables-dir", "out/tables"))
  dir.create(adir, recursive = TRUE, showWarnings = FALSE)
  dir.create(tdir, recursive = TRUE, showWarnings = FALSE)
  spec <- fromJSON(file.path(ROOT, "tools", "comms", "abstract_slots.json"), simplifyVector = FALSE)
  ledger <- fromJSON(ledger_path, simplifyVector = FALSE)
  d <- cells_from_ledger(ledger, spec)
  if (all(is.na(d$point))) {
    message("build_exhibits: the ledger holds no T1_* cell; run export_numbers.R after W3.16")
    return(1L)
  }
  d$cell <- cell_text(d)
  write.csv(d[, c("row", "col", "slot", "units", "point", "lo95", "hi95", "print_point",
                  "print_lo95", "print_hi95", "source")],
            tagged(tdir, "table1_data.csv", tag), row.names = FALSE, na = "")

  # ---- table1.md
  rows <- vapply(spec$table1$rows, `[[`, "", 1)
  cols <- vapply(spec$table1$cols, `[[`, "", 1)
  wide <- sapply(cols, function(c) d$cell[d$col == c][match(rows, d$row[d$col == c])])
  labels <- vapply(spec$table1$rows, `[[`, "", 2)
  heads <- vapply(spec$table1$cols, `[[`, "", 2)
  md <- c(CAPTION, "",
          paste0("| Component | ", paste(heads, collapse = " | "), " |"),
          paste0("|---|", paste(rep("---:", length(heads)), collapse = "|"), "|"),
          paste0("| ", labels, " | ", apply(wide, 1, paste, collapse = " | "), " |"))
  writeLines(md, tagged(adir, "table1.md", tag))

  # ---- table1.inline.md: for a form with no upload field (SOP W6.12, about 60 words).
  # Results already prints both areas, so the inline table carries what the text does
  # not: the top and bottom edge of the two regime components, in inches.
  keep_r <- c("BUF", "ABS"); keep_c <- c("TOP", "BOT")
  name_word <- c(TOP = "top edge", BOT = "bottom edge")
  inline <- vapply(keep_r, function(r) {
    lab <- labels[match(r, rows)]
    parts <- vapply(keep_c, function(c) {
      paste(name_word[[c]], d$cell[d$row == r & d$col == c])
    }, "")
    paste0(lab, ": ", paste(parts, collapse = "; "), ".")
  }, "")
  writeLines(c("Table 1, inches, 95% intervals in brackets.", unname(inline)),
             tagged(adir, "table1.inline.md", tag))

  # ---- table1.png
  g <- gridExtra::tableGrob(
    cbind(Component = labels, stats::setNames(as.data.frame(wide), heads)),
    rows = NULL, theme = gridExtra::ttheme_minimal(base_size = 7, padding = grid::unit(c(3, 2), "mm"))
  )
  cap <- grid::textGrob(paste(strwrap(CAPTION, 140), collapse = "\n"), x = grid::unit(2, "mm"),
                        hjust = 0, gp = grid::gpar(fontsize = 6.5))
  ragg::agg_png(tagged(adir, "table1.png", tag), width = 17, height = 4.6, units = "cm", res = 600,
                background = "white")
  grid::grid.draw(gridExtra::arrangeGrob(g, top = cap))
  grDevices::dev.off()

  # ---- figure1: 8 cm wide, grayscale, one panel per quantity in a 2 x 2 grid, one row
  # per component, a point and its 95% interval. One series, so no legend and no colour.
  f <- d[!is.na(d$point), ]
  f$row_label <- factor(FIG_ROWS[f$row], levels = rev(unname(FIG_ROWS)))
  f$col_label <- factor(f$col_label, levels = heads)
  write.csv(f[, c("row", "col", "slot", "units", "point", "lo95", "hi95", "source")],
            tagged(tdir, "figure1_data.csv", tag), row.names = FALSE, na = "")
  p <- ggplot(f, aes(x = point, y = row_label)) +
    geom_vline(xintercept = 0, colour = "grey50", linewidth = 0.3, linetype = "22") +
    geom_errorbar(aes(xmin = lo95, xmax = hi95), orientation = "y", width = 0, linewidth = 0.45,
                  colour = "black", na.rm = TRUE) +
    geom_point(size = 1.3, colour = "black") +
    facet_wrap(~col_label, nrow = 2, scales = "free_x") +
    scale_x_continuous(breaks = scales::breaks_pretty(n = 3), labels = function(x) format(x, trim = TRUE)) +
    expand_limits(x = 0) +
    labs(x = "Change: point estimate and 95% interval", y = NULL) +
    theme_minimal(base_size = 7) +
    theme(panel.grid.minor = element_blank(), panel.grid.major.y = element_blank(),
          panel.grid.major.x = element_line(colour = "grey88", linewidth = 0.25),
          strip.text = element_text(face = "bold", size = 7, hjust = 0),
          axis.text = element_text(colour = "grey15", size = 6.5),
          axis.title.x = element_text(size = 6.5, colour = "grey15"),
          panel.spacing.x = grid::unit(3, "mm"), panel.spacing.y = grid::unit(2, "mm"),
          plot.margin = grid::unit(c(1, 2, 1, 1), "mm"))
  ragg::agg_png(tagged(adir, "figure1.png", tag), width = 8, height = 6.5, units = "cm",
                res = 600, background = "white")
  print(p)
  grDevices::dev.off()

  area <- d[d$col == "AREA" & !is.na(d$point), ]
  alt <- paste0(
    "Figure 1. Dot-and-interval chart in four panels: top edge, bottom edge, half-width ",
    "in inches, and area in square inches. Each panel shows the pre-trend per season, the ",
    "2025 buffer change, the 2026 challenge-system change and the plate-plane shift, each ",
    "with its 95% interval, against a dashed zero line. Area changes: ",
    paste0(tolower(area$row_label), " ", area$cell, collapse = "; "), "."
  )
  writeLines(alt, tagged(adir, "figure1.alt.txt", tag))
  cat(sprintf("build_exhibits: table1 %d of %d cells filled; figure1 %d rows; tag '%s'\n",
              sum(!is.na(d$point)), nrow(d), nrow(f), tag))
  0L
}

if (sys.nframe() == 0L) {
  status <- tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
    message("build_exhibits: ", conditionMessage(e))
    2L
  })
  quit(status = status)
}
