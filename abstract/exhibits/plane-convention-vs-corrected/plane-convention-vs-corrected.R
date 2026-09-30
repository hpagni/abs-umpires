#!/usr/bin/env Rscript
# Candidate exhibit: plane-convention-vs-corrected (figure).
# The 2025-to-2026 zone-area change under the published convention
# (2025 at the front of the plate, 2026 at mid-plate) and with both
# seasons at mid-plate, plus the plane component alone.
#
# Reads ONLY two committed tables under out/ch1/tab. No fit object is
# loaded and no new fit is made. Every number that appears in the PNG,
# SVG, caption, alt text and data-sources listing is read from a table
# row by this script. Run from the repository root:
#   Rscript abstract/exhibits/plane-convention-vs-corrected/plane-convention-vs-corrected.R

suppressPackageStartupMessages(library(ggplot2))

root <- getwd()
stopifnot(dir.exists(file.path(root, "out", "ch1", "tab")))  # run from the repository root
out_dir <- file.path(root, "abstract", "exhibits", "plane-convention-vs-corrected")
slug <- "plane-convention-vs-corrected"

# ---- sources -----------------------------------------------------------------
src_t4 <- "out/ch1/tab/T4_plane_component.csv"
src_t9 <- "out/ch1/tab/T9_published_comparison.csv"

t4 <- read.csv(file.path(root, src_t4), stringsAsFactors = FALSE)
t9 <- read.csv(file.path(root, src_t9), stringsAsFactors = FALSE)

a4 <- t4[t4$estimand == "area_sqin", ]
a9 <- t9[t9$quantity == "area_sqin", ]
stopifnot(nrow(a4) == 1, nrow(a9) == 1, a4$units == "sq in")

# Columns read from T4_plane_component.csv, row estimand == "area_sqin"
pub_pt <- a4$published_convention_change_point
pub_lo <- a4$published_convention_change_lo95
pub_hi <- a4$published_convention_change_hi95
cor_pt <- a4$corrected_change_point
cor_lo <- a4$corrected_change_lo95
cor_hi <- a4$corrected_change_hi95
pl_pt  <- a4$point
pl_lo  <- a4$lo95
pl_hi  <- a4$hi95
th_mid   <- a4$theta_2025_mid
th_front <- a4$theta_2025_front

# Columns read from T9_published_comparison.csv, row quantity == "area_sqin"
band_lo <- a9$published_lo95
band_hi <- a9$published_hi95
convention_text <- a9$published_convention

# Consistency guards: the two tables carry the same change columns.
stopifnot(isTRUE(all.equal(pub_pt, a9$published_convention_change_point)),
          isTRUE(all.equal(cor_pt, a9$corrected_change_point)),
          isTRUE(all.equal(pl_pt, a9$plane_component_point)),
          band_lo < band_hi)

# ---- formatting ----------------------------------------------------------------
f1 <- function(x) {
  s <- formatC(x, format = "f", digits = 1)
  gsub("-", "−", s, fixed = TRUE)
}
fint <- function(pt, lo, hi) sprintf("%s (%s to %s)", f1(pt), f1(lo), f1(hi))
fsigned <- function(x) if (x > 0) paste0("+", f1(x)) else f1(x)
f0 <- function(x) gsub("-", "−", formatC(x, format = "f", digits = 0), fixed = TRUE)
f2 <- function(x) gsub("-", "−", formatC(x, format = "f", digits = 2), fixed = TRUE)

rows <- data.frame(
  y = c(3, 2, 1),
  kind = c("change", "change", "plane"),
  point = c(pub_pt, cor_pt, pl_pt),
  lo = c(pub_lo, cor_lo, pl_lo),
  hi = c(pub_hi, cor_hi, pl_hi),
  label = c(
    "2025 to 2026, as published work measures it\n(2025 at the front of the plate, 2026 at mid-plate)",
    "2025 to 2026, both seasons at mid-plate",
    sprintf("Plane component alone: 2025 at mid-plate minus 2025 at the front\n(%s minus %s sq in)",
            f2(th_mid), f2(th_front))
  ),
  stringsAsFactors = FALSE
)
rows$value <- mapply(function(p, l, h) fint(p, l, h), rows$point, rows$lo, rows$hi)
rows$value[3] <- paste0("+", rows$value[3])

# ---- figure ------------------------------------------------------------------
ink   <- "#1a1a19"
band  <- "#e4e4e1"
grid  <- "#d9d9d6"
muted <- "#5c5c58"

x_min <- -45
x_max <- 25
lab_dy <- 0.24           # label block sits this far above the interval
top_y <- 4.02

p <- ggplot(rows) +
  annotate("rect", xmin = band_lo, xmax = band_hi, ymin = 0.55, ymax = top_y,
           fill = band, colour = NA) +
  annotate("text", x = (band_lo + band_hi) / 2, y = top_y - 0.02,
           label = sprintf("Published 95%% range\n%s to %s sq in", f0(band_lo), f0(band_hi)),
           size = 8 / .pt, colour = muted, vjust = 1, lineheight = 0.95) +
  geom_vline(xintercept = 0, linetype = "22", colour = ink, linewidth = 0.4) +
  geom_segment(aes(x = lo, xend = hi, y = y, yend = y), colour = ink, linewidth = 0.7,
               lineend = "butt") +
  geom_point(aes(x = point, y = y, shape = kind), colour = ink, fill = "white",
             size = 2.6, stroke = 0.8) +
  geom_text(aes(x = x_min, y = y + lab_dy, label = label), hjust = 0, vjust = 0,
            size = 9 / .pt, colour = ink, lineheight = 0.95) +
  geom_text(aes(x = x_max, y = y + lab_dy, label = value), hjust = 1, vjust = 0,
            size = 9 / .pt, colour = ink, fontface = "bold") +
  scale_shape_manual(values = c(change = 16, plane = 23), guide = "none") +
  scale_x_continuous(limits = c(x_min, x_max), breaks = seq(-40, 20, by = 10),
                     labels = function(b) gsub("-", "−", b, fixed = TRUE),
                     expand = c(0, 0)) +
  scale_y_continuous(limits = c(0.55, top_y), expand = c(0, 0)) +
  labs(x = "Change in the area of the 50% strike-zone contour, sq in (point and 95% interval)",
       y = NULL) +
  theme_minimal(base_size = 9, base_family = "Helvetica") +
  theme(
    panel.grid.major.y = element_blank(),
    panel.grid.minor = element_blank(),
    panel.grid.major.x = element_line(colour = grid, linewidth = 0.3),
    axis.text.y = element_blank(),
    axis.ticks.y = element_blank(),
    axis.text.x = element_text(colour = ink, size = 8.5),
    axis.title.x = element_text(colour = ink, size = 9, margin = margin(t = 6)),
    axis.ticks.x = element_line(colour = grid, linewidth = 0.3),
    axis.line.x = element_line(colour = grid, linewidth = 0.4),
    plot.background = element_rect(fill = "white", colour = NA),
    panel.background = element_rect(fill = "white", colour = NA),
    plot.margin = margin(t = 4, r = 6, b = 4, l = 6)
  )

w_in <- 6.5
h_in <- 3.2
ggsave(file.path(out_dir, paste0(slug, ".png")), p, width = w_in, height = h_in,
       units = "in", dpi = 300, device = grDevices::png, type = "cairo", bg = "white")
ggsave(file.path(out_dir, paste0(slug, ".svg")), p, width = w_in, height = h_in,
       units = "in", device = grDevices::svg, bg = "white")

# ---- caption, alt text, data sources (numbers from the same rows) ------------
caption <- sprintf(paste(
  "Change in strike-zone area, 2025 to 2026, as published work measures it",
  "(2025 at the front of the plate, 2026 at mid-plate) and with both seasons at",
  "mid-plate. The plane component is 2025 read at mid-plate minus at the front.",
  "Points with 95%% intervals; the grey band is the published range of %s to %s sq in."),
  f0(band_lo), f0(band_hi))
stopifnot(length(strsplit(caption, "\\s+")[[1]]) < 60)
writeLines(caption, file.path(out_dir, "caption.md"))

alt <- sprintf(paste(
  "Dot-and-interval chart of three quantities in square inches with a dashed line at zero",
  "and a grey band from %s to %s marked as the published 95%% range.",
  "2025 to 2026 as published work measures it, 2025 at the front of the plate and 2026 at mid-plate: %s.",
  "2025 to 2026 with both seasons at mid-plate: %s.",
  "Plane component alone, 2025 at mid-plate minus 2025 at the front: %s."),
  f0(band_lo), f0(band_hi), rows$value[1], rows$value[2], rows$value[3])
stopifnot(nchar(alt) >= 40)
writeLines(alt, file.path(out_dir, "alt.txt"))

ds <- c(
  "# Data sources for plane-convention-vs-corrected",
  "",
  "Every number on the figure, in the caption and in the alt text is read by",
  "`plane-convention-vs-corrected.R` from the rows and columns below. No fit object",
  "is loaded; no new fit is made; no per-game, per-pitch, per-player or per-umpire",
  "datum is read. Values are printed to one decimal (band limits to zero decimals; the two 2025",
  "area levels in the row 3 label to two decimals, so their difference rounds to the",
  "printed plane component).",
  "",
  sprintf("## `%s`, row `estimand == \"area_sqin\"` (units column: `%s`)", src_t4, a4$units),
  "",
  "| column | value | where it appears |",
  "|---|---:|---|",
  sprintf("| `published_convention_change_point` | %s | row 1 dot; printed %s |", pub_pt, f1(pub_pt)),
  sprintf("| `published_convention_change_lo95` | %s | row 1 interval; printed %s |", pub_lo, f1(pub_lo)),
  sprintf("| `published_convention_change_hi95` | %s | row 1 interval; printed %s |", pub_hi, f1(pub_hi)),
  sprintf("| `corrected_change_point` | %s | row 2 dot; printed %s |", cor_pt, f1(cor_pt)),
  sprintf("| `corrected_change_lo95` | %s | row 2 interval; printed %s |", cor_lo, f1(cor_lo)),
  sprintf("| `corrected_change_hi95` | %s | row 2 interval; printed %s |", cor_hi, f1(cor_hi)),
  sprintf("| `point` | %s | row 3 diamond; printed +%s |", pl_pt, f1(pl_pt)),
  sprintf("| `lo95` | %s | row 3 interval; printed %s |", pl_lo, f1(pl_lo)),
  sprintf("| `hi95` | %s | row 3 interval; printed %s |", pl_hi, f1(pl_hi)),
  sprintf("| `theta_2025_mid` | %s | row 3 label; printed %s |", th_mid, f2(th_mid)),
  sprintf("| `theta_2025_front` | %s | row 3 label; printed %s |", th_front, f2(th_front)),
  sprintf("| `units` | %s | guard that the row is in sq in |", a4$units),
  "",
  sprintf("## `%s`, row `quantity == \"area_sqin\"`", src_t9),
  "",
  "| column | value | where it appears |",
  "|---|---:|---|",
  sprintf("| `published_lo95` | %s | left edge of the grey band; printed %s |", band_lo, f0(band_lo)),
  sprintf("| `published_hi95` | %s | right edge of the grey band; printed %s |", band_hi, f0(band_hi)),
  sprintf("| `published_convention` | %s | wording of the row 1 label (paraphrased) |", convention_text),
  "| `published_convention_change_point`, `corrected_change_point`, `plane_component_point` | as in T4 | equality guard against the T4 row; not drawn |",
  "",
  "## Numbers that appear, with source",
  "",
  sprintf("- %s: T4 `published_convention_change_point/_lo95/_hi95`.", rows$value[1]),
  sprintf("- %s: T4 `corrected_change_point/_lo95/_hi95`.", rows$value[2]),
  sprintf("- %s: T4 `point/lo95/hi95` (component `plane`).", rows$value[3]),
  sprintf("- %s minus %s sq in: T4 `theta_2025_mid`, `theta_2025_front`.", f2(th_mid), f2(th_front)),
  sprintf("- %s to %s sq in: T9 `published_lo95`, `published_hi95`.", f0(band_lo), f0(band_hi)),
  "- 0: the dashed reference line, not a datum.",
  "- Axis ticks −40 to 20 by 10: axis scale, not data.",
  "",
  "Intervals are 95% throughout, as the column names state. The published range is",
  "the 95% interval reported by the article named in T9 `published_source`; the",
  "article title is not printed on the figure."
)
writeLines(ds, file.path(out_dir, "data-sources.md"))

# Echo the numbers so a reader of the log can compare them with the tables.
cat(sprintf("row 1 published convention: %s\n", rows$value[1]))
cat(sprintf("row 2 both mid-plate:       %s\n", rows$value[2]))
cat(sprintf("row 3 plane component:      %s\n", rows$value[3]))
cat(sprintf("theta_2025 mid/front:       %s / %s\n", f2(th_mid), f2(th_front)))
cat(sprintf("published band:             %s to %s\n", f0(band_lo), f0(band_hi)))
cat(sprintf("caption words: %d; alt chars: %d\n",
            length(strsplit(caption, "\\s+")[[1]]), nchar(alt)))
