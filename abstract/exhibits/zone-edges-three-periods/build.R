# abstract/exhibits/zone-edges-three-periods/build.R
#
# Candidate exhibit for the SSAC 2027 abstract: fitted 50 percent zone edges by season, drawn
# to scale over the rule-book rectangle for a 72-inch batter, catcher's view, in inches.
#
# Reads ONLY committed tables under out/ch1/tab and the constant lines of R/lib/zone.R and
# R/lib/ch1_fits.R. No model object is opened and no fit is run. Every number printed on the
# figure is read here from a table row or a sourced constant; nothing is typed by hand.
#
# Run from the repository root:
#   Rscript abstract/exhibits/zone-edges-three-periods/build.R
#
# Writes, next to this script: zone-edges-three-periods.png (300 dpi, 6.5 x 5.5 in),
# zone-edges-three-periods.svg, and data-sources.md (the rows and columns read, and every
# number that appears on the figure).

suppressPackageStartupMessages({
  library(ggplot2)
  library(grid)
})

root    <- normalizePath(".", mustWork = TRUE)
out_dir <- file.path(root, "abstract", "exhibits", "zone-edges-three-periods")
stopifnot(file.exists(file.path(root, "out", "ch1", "tab", "T3_estimands.csv")))
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

## --- constants, read from the library files rather than retyped ---------------------------

# Evaluate exactly the assignment line `NAME <- value  # comment` from a source file. The
# library files also define loaders and guards, so only the named constant lines are evaluated.
read_constant <- function(path, name) {
  lines <- readLines(path, warn = FALSE)
  pat   <- sprintf("^%s\\s*<-\\s*", name)
  hit   <- grep(pat, lines, value = TRUE)
  stopifnot(length(hit) == 1L)
  rhs <- sub("#.*$", "", sub(pat, "", hit))
  eval(parse(text = rhs), envir = baseenv())
}
zone_R <- file.path(root, "R", "lib", "zone.R")
fits_R <- file.path(root, "R", "lib", "ch1_fits.R")
PLATE_HALF_W_FT <- read_constant(zone_R, "PLATE_HALF_W_FT")
ABS_TOP_FRAC    <- read_constant(zone_R, "ABS_TOP_FRAC")
ABS_BOT_FRAC    <- read_constant(zone_R, "ABS_BOT_FRAC")
REF_HEIGHT_IN   <- read_constant(fits_R, "REF_HEIGHT_IN")
ZN_MID          <- read_constant(fits_R, "ZN_MID")
CENTRE_X_FT     <- read_constant(fits_R, "CENTRE_X_FT")

rb_half_w_in <- PLATE_HALF_W_FT * 12                # 8.5 in
rb_top_in    <- ABS_TOP_FRAC * REF_HEIGHT_IN         # 38.52 in
rb_bot_in    <- ABS_BOT_FRAC * REF_HEIGHT_IN         # 19.44 in
centre_x_in  <- CENTRE_X_FT * 12                     # 3 in

## --- tables --------------------------------------------------------------------------------

t3 <- read.csv(file.path(root, "out", "ch1", "tab", "T3_estimands.csv"), stringsAsFactors = FALSE)
t4 <- read.csv(file.path(root, "out", "ch1", "tab", "T4_decomposition.csv"), stringsAsFactors = FALSE)

edges_wanted <- c("top_in", "bot_in", "half_width_in", "area_sqin")
e <- t3[t3$fit == "main" & t3$arm == "primary" & t3$estimand %in% edges_wanted,
        c("season", "estimand", "units", "point", "lo95", "hi95")]
stopifnot(nrow(e) == 20L, all(table(e$estimand) == 5L), all(sort(unique(e$season)) == 2022:2026))
stopifnot(all(e$units[e$estimand == "area_sqin"] == "sq in"), all(e$units[e$estimand != "area_sqin"] == "in"))

get <- function(season, est, col = "point") {
  v <- e[e$season == season & e$estimand == est, col]
  stopifnot(length(v) == 1L)
  v
}

comp_wanted <- c("delta_buffer", "delta_abs")
d <- t4[t4$fit == "main" & t4$arm == "primary" & t4$estimand %in% c("top_in", "bot_in", "half_width_in") &
          t4$component %in% comp_wanted, c("estimand", "component", "units", "point", "lo95", "hi95")]
stopifnot(nrow(d) == 6L, all(d$units == "in"))

## --- derived frames ------------------------------------------------------------------------

seasons <- 2022:2026
period_of <- c("2022" = "2022-2024", "2023" = "2022-2024", "2024" = "2022-2024",
               "2025" = "2025, grading buffer 0.75 in", "2026" = "2026, ABS challenges")
rects <- data.frame(
  season = seasons,
  period = period_of[as.character(seasons)],
  top    = sapply(seasons, get, "top_in"),
  bot    = sapply(seasons, get, "bot_in"),
  hw     = sapply(seasons, get, "half_width_in"),
  area   = sapply(seasons, get, "area_sqin"),
  stringsAsFactors = FALSE
)
rects$period <- factor(rects$period, levels = unname(unique(period_of)))

# Whiskers: 95% intervals on each fitted edge, drawn at the place the edge is read.
# top and bottom are averaged over |x| <= centre_x_in, so the whisker sits at x = 0;
# the half-width is read at mid-height, so the side whiskers sit at the rectangle's mid-height.
wh <- do.call(rbind, lapply(seasons, function(s) {
  mid <- (get(s, "top_in") + get(s, "bot_in")) / 2
  rbind(
    data.frame(season = s, x = 0,  xend = 0,  y = get(s, "top_in", "lo95"), yend = get(s, "top_in", "hi95")),
    data.frame(season = s, x = 0,  xend = 0,  y = get(s, "bot_in", "lo95"), yend = get(s, "bot_in", "hi95")),
    data.frame(season = s, x =  get(s, "half_width_in", "lo95"), xend =  get(s, "half_width_in", "hi95"), y = mid, yend = mid),
    data.frame(season = s, x = -get(s, "half_width_in", "hi95"), xend = -get(s, "half_width_in", "lo95"), y = mid, yend = mid)
  )
}))
wh$period <- factor(period_of[as.character(wh$season)], levels = levels(rects$period))
widest_half95 <- max(c(sapply(seasons, function(s) get(s, "top_in", "hi95") - get(s, "top_in", "lo95")),
                       sapply(seasons, function(s) get(s, "bot_in", "hi95") - get(s, "bot_in", "lo95")),
                       sapply(seasons, function(s) get(s, "half_width_in", "hi95") - get(s, "half_width_in", "lo95")))) / 2

# Area labels: one per season, in a column to the right of the outlines, each with a leader
# from that season's right edge at the label's height, so the edge offsets stay visible.
lab_x   <- 13.2
lab_z   <- c("2022" = 41.6, "2023" = 39.4, "2024" = 37.2, "2025" = 33.6, "2026" = 31.4)
labs_df <- data.frame(
  season = seasons,
  period = rects$period,
  x0     = rects$hw,
  x1     = lab_x - 0.4,
  z      = lab_z[as.character(seasons)],
  text   = sprintf("%d   %.1f sq in", seasons, rects$area),
  stringsAsFactors = FALSE
)

## --- colours (dataviz reference palette; grey is the de-emphasised pre-period) ------------
col_period <- c("2022-2024" = "#7a7a76",
                "2025, grading buffer 0.75 in" = "#eb6834",
                "2026, ABS challenges" = "#4a3aa7")
lw_period  <- c("2022-2024" = 0.35, "2025, grading buffer 0.75 in" = 0.75, "2026, ABS challenges" = 0.75)
ink  <- "#0b0b0b"; ink2 <- "#52514e"; surface <- "#ffffff"; rb_fill <- "#ebebe8"; rb_line <- "#c9c9c4"

## --- inset: edge steps net of the 2022-2024 trend (T4 delta_buffer, delta_abs) -------------
d$edge <- factor(c(top_in = "Top edge", bot_in = "Bottom edge", half_width_in = "Half-width")[d$estimand],
                 levels = rev(c("Top edge", "Bottom edge", "Half-width")))
d$step <- factor(c(delta_buffer = "2025 step", delta_abs = "2026 step")[d$component],
                 levels = c("2025 step", "2026 step"))
d$col  <- c(delta_buffer = col_period[[2]], delta_abs = col_period[[3]])[d$component]
d$lab  <- sprintf("%+.2f", d$point)
d$lab_x <- ifelse(d$point < 0, d$lo95 - 0.04, d$hi95 + 0.04)
d$lab_h <- ifelse(d$point < 0, 1, 0)

inset <- ggplot(d, aes(y = edge, colour = step, group = step)) +
  geom_vline(xintercept = 0, linetype = "22", linewidth = 0.3, colour = ink2) +
  geom_errorbar(aes(xmin = lo95, xmax = hi95), width = 0, linewidth = 0.5, orientation = "y",
                position = position_dodge(width = 0.6)) +
  geom_point(aes(x = point), size = 1.6, position = position_dodge(width = 0.6)) +
  geom_text(aes(x = lab_x, label = lab, hjust = lab_h), size = 8 / .pt, colour = ink,
            position = position_dodge(width = 0.6), show.legend = FALSE) +
  scale_colour_manual(values = c("2025 step" = col_period[[2]], "2026 step" = col_period[[3]]), name = NULL) +
  scale_x_continuous(limits = c(-1.15, 1.15), breaks = c(-1, -0.5, 0, 0.5, 1)) +
  labs(x = "Step net of the 2022-2024 trend, in (95%)", y = NULL,
       title = "Edge steps, in") +
  theme_minimal(base_size = 8) +
  theme(panel.grid = element_blank(),
        panel.background = element_rect(fill = surface, colour = NA),
        plot.background = element_rect(fill = surface, colour = rb_line, linewidth = 0.3),
        plot.title = element_text(size = 8, face = "bold", colour = ink, margin = margin(b = 2)),
        axis.text = element_text(size = 8, colour = ink),
        axis.title.x = element_text(size = 8, colour = ink2, margin = margin(t = 2)),
        axis.ticks.x = element_line(colour = ink2, linewidth = 0.3),
        axis.line.x = element_line(colour = ink2, linewidth = 0.3),
        legend.position = "bottom", legend.text = element_text(size = 8, colour = ink),
        legend.key.height = unit(6, "pt"), legend.key.width = unit(10, "pt"),
        legend.margin = margin(0, 0, 0, 0), legend.box.margin = margin(-4, 0, 0, 0),
        plot.margin = margin(4, 6, 3, 4))
inset_grob <- ggplotGrob(inset)

## --- main panel ----------------------------------------------------------------------------
x_lim <- c(-13.0, 22.6)
z_lim <- c(13.6, 44.2)
note <- sprintf(paste0(
  "Outlines are fitted 50 percent edge positions for a %d-in batter at the 2024 pitch mix: top and bottom\n",
  "averaged over |x| <= %g in, sides read at mid-height (zn = %s); they are not the full contour.\n",
  "Whiskers at the middle of each edge are 95%% intervals; the widest is +/-%.2f in, about the printed line width."),
  REF_HEIGHT_IN, centre_x_in, format(ZN_MID), widest_half95)

p <- ggplot() +
  # rule-book rectangle
  annotate("rect", xmin = -rb_half_w_in, xmax = rb_half_w_in, ymin = rb_bot_in, ymax = rb_top_in,
           fill = rb_fill, colour = rb_line, linewidth = 0.3) +
  annotate("text", x = 0, y = rb_bot_in + 0.5, hjust = 0.5, vjust = 0, size = 8 / .pt, colour = ink2,
           lineheight = 1.05,
           label = sprintf("Rule-book zone, %d-in batter\n%g in wide, %.1f to %.1f in high",
                           REF_HEIGHT_IN, 2 * rb_half_w_in, rb_bot_in, rb_top_in)) +
  # fitted rectangles, pre-period first so the highlighted seasons draw on top
  geom_rect(data = rects[order(rects$period), ],
            aes(xmin = -hw, xmax = hw, ymin = bot, ymax = top, colour = period, linewidth = period),
            fill = NA) +
  geom_segment(data = wh, aes(x = x, xend = xend, y = y, yend = yend, colour = period),
               linewidth = 0.4, show.legend = FALSE) +
  # area labels with leaders
  geom_segment(data = labs_df, aes(x = x0, xend = x1, y = z, yend = z, colour = period),
               linewidth = 0.3, linetype = "12", show.legend = FALSE) +
  geom_point(data = labs_df, aes(x = x0, y = z, colour = period), size = 1.1, show.legend = FALSE) +
  geom_text(data = labs_df, aes(x = lab_x, y = z, label = text), hjust = 0, size = 8 / .pt, colour = ink) +
  annotate("text", x = lab_x, y = max(lab_z) + 1.9, hjust = 0, vjust = 0, size = 8 / .pt, colour = ink2,
           label = "Area of the fitted zone") +
  annotation_custom(inset_grob, xmin = -8.1, xmax = 8.1, ymin = 23.0, ymax = 37.8) +
  scale_colour_manual(values = col_period, name = NULL, breaks = levels(rects$period)) +
  scale_linewidth_manual(values = lw_period, name = NULL, breaks = levels(rects$period)) +
  scale_x_continuous(limits = x_lim, breaks = seq(-12, 12, by = 6), expand = c(0, 0)) +
  scale_y_continuous(limits = z_lim, breaks = seq(15, 45, by = 5), expand = c(0, 0)) +
  coord_fixed(ratio = 1, clip = "off") +
  labs(x = "Horizontal position from the plate centre, in (catcher's view)",
       y = "Height above the ground, in",
       caption = note) +
  guides(colour = guide_legend(override.aes = list(fill = NA, linewidth = c(0.5, 0.9, 0.9))),
         linewidth = "none") +
  theme_minimal(base_size = 9) +
  theme(text = element_text(colour = ink),
        plot.background = element_rect(fill = surface, colour = NA),
        panel.background = element_rect(fill = surface, colour = NA),
        panel.grid.major = element_line(colour = "#f0f0ee", linewidth = 0.3),
        panel.grid.minor = element_blank(),
        axis.text = element_text(size = 8, colour = ink),
        axis.title = element_text(size = 9, colour = ink2),
        axis.title.x = element_text(margin = margin(t = 4)),
        axis.title.y = element_text(margin = margin(r = 4)),
        axis.line = element_line(colour = ink2, linewidth = 0.3),
        axis.ticks = element_line(colour = ink2, linewidth = 0.3),
        legend.position = "top", legend.justification = "left",
        legend.text = element_text(size = 9, colour = ink),
        legend.key.width = unit(16, "pt"), legend.key.height = unit(9, "pt"),
        legend.margin = margin(0, 0, 0, 0), legend.box.margin = margin(0, 0, 2, 0),
        plot.caption = element_text(size = 8, colour = ink2, hjust = 0, lineheight = 1.15,
                                    margin = margin(t = 6)),
        plot.caption.position = "plot",
        plot.margin = margin(6, 8, 6, 6))

W <- 6.5; H <- 5.5
ggsave(file.path(out_dir, "zone-edges-three-periods.png"), p, width = W, height = H, units = "in",
       dpi = 300, device = ragg::agg_png, bg = surface)
ggsave(file.path(out_dir, "zone-edges-three-periods.svg"), p, width = W, height = H, units = "in",
       device = grDevices::svg, bg = surface)

## --- data-sources.md, written from the same filters the plot used -------------------------
fmt <- function(x, k = 2) formatC(x, format = "f", digits = k)
src <- c(
  "# Data sources: zone-edges-three-periods",
  "",
  "Written by build.R from the same filters that drew the figure. No model object was read; no fit was run.",
  "",
  "## Files, rows and columns read",
  "",
  "- `out/ch1/tab/T3_estimands.csv`: rows `fit == \"main\"`, `arm == \"primary\"`, `estimand` in",
  "  {top_in, bot_in, half_width_in, area_sqin}, `season` 2022..2026 (20 rows); columns `season`,",
  "  `estimand`, `units`, `point`, `lo95`, `hi95`.",
  "- `out/ch1/tab/T4_decomposition.csv`: rows `fit == \"main\"`, `arm == \"primary\"`, `estimand` in",
  "  {top_in, bot_in, half_width_in}, `component` in {delta_buffer, delta_abs} (6 rows); columns",
  "  `estimand`, `component`, `units`, `point`, `lo95`, `hi95`.",
  "- `R/lib/zone.R`: the assignment lines `PLATE_HALF_W_FT`, `ABS_TOP_FRAC`, `ABS_BOT_FRAC` (evaluated, not retyped).",
  "- `R/lib/ch1_fits.R`: the assignment lines `REF_HEIGHT_IN`, `ZN_MID`, `CENTRE_X_FT` (evaluated, not retyped).",
  "",
  "## Numbers that appear on the figure",
  "",
  "Rule-book rectangle (constants):",
  sprintf("  PLATE_HALF_W_FT x 12 = %s in (printed as %g in wide); bottom ABS_BOT_FRAC x REF_HEIGHT_IN = %s in;",
          fmt(rb_half_w_in), 2 * rb_half_w_in, fmt(rb_bot_in)),
  sprintf("  top ABS_TOP_FRAC x REF_HEIGHT_IN = %s in; centre window CENTRE_X_FT x 12 = %g in; ZN_MID = %s.",
          fmt(rb_top_in), centre_x_in, format(ZN_MID)),
  "",
  "Fitted rectangles and whiskers (T3_estimands.csv, point [lo95, hi95], in):",
  "",
  "| season | top_in | bot_in | half_width_in | area_sqin (label) |",
  "|---|---|---|---|---|",
  sapply(seasons, function(s) sprintf("| %d | %s [%s, %s] | %s [%s, %s] | %s [%s, %s] | %s [%s, %s] (%s) |", s,
    fmt(get(s, "top_in")), fmt(get(s, "top_in", "lo95")), fmt(get(s, "top_in", "hi95")),
    fmt(get(s, "bot_in")), fmt(get(s, "bot_in", "lo95")), fmt(get(s, "bot_in", "hi95")),
    fmt(get(s, "half_width_in")), fmt(get(s, "half_width_in", "lo95")), fmt(get(s, "half_width_in", "hi95")),
    fmt(get(s, "area_sqin"), 1), fmt(get(s, "area_sqin", "lo95"), 1), fmt(get(s, "area_sqin", "hi95"), 1),
    sprintf("%.1f sq in", get(s, "area_sqin")))),
  "",
  sprintf("Widest 95%% half-interval over the fifteen edge rows (printed in the note): %.2f in.", widest_half95),
  "",
  "Inset, edge steps net of the 2022-2024 trend (T4_decomposition.csv, point [lo95, hi95], in; label prints the point):",
  "",
  "| estimand | component | point | lo95 | hi95 |",
  "|---|---|---|---|---|",
  sprintf("| %s | %s | %s | %s | %s |", d$estimand, d$component, fmt(d$point), fmt(d$lo95), fmt(d$hi95)),
  "",
  "Period labels are descriptive: 2022-2024; 2025, grading buffer 0.75 in; 2026, ABS challenges.",
  "The area intervals are not drawn (the label carries the point only); they are listed above for the record."
)
writeLines(src, file.path(out_dir, "data-sources.md"))

## --- caption and alt text, numbers filled from the same rows ------------------------------
step <- function(est, comp) d$point[d$estimand == est & d$component == comp]
caption <- sprintf(paste0(
  "Fitted 50 percent zone edges by season for a %d-inch batter at the 2024 pitch mix, to scale over ",
  "the rule-book rectangle, catcher's view. The 2022-2024 outlines nearly coincide; the 2025 outline ",
  "is narrower at the sides and the 2026 outline shorter at top and bottom. Inset: edge steps net ",
  "of the 2022-2024 trend, 95%% intervals."), REF_HEIGHT_IN)
stopifnot(length(strsplit(caption, "\\s+")[[1]]) < 60)
writeLines(caption, file.path(out_dir, "caption.md"))

alt <- sprintf(paste0(
  "Rectangles drawn to scale in inches, catcher's view, showing the fitted 50 percent strike-zone edges for ",
  "each season 2022 to 2026 for a %d-inch batter over the light rule-book zone (%g inches wide, %.1f to %.1f ",
  "inches high). The three 2022-2024 outlines in grey nearly coincide; the 2025 outline is narrower at the ",
  "sides; the 2026 outline is shorter at the top and bottom. Fitted areas: %s square inches. Inset: edge steps ",
  "net of the 2022-2024 trend with 95%% intervals: 2025 top %+.2f, bottom %+.2f, half-width %+.2f inches; ",
  "2026 top %+.2f, bottom %+.2f, half-width %+.2f inches."),
  REF_HEIGHT_IN, 2 * rb_half_w_in, rb_bot_in, rb_top_in,
  paste(sprintf("%d %.1f", rects$season, rects$area), collapse = ", "),
  step("top_in", "delta_buffer"), step("bot_in", "delta_buffer"), step("half_width_in", "delta_buffer"),
  step("top_in", "delta_abs"), step("bot_in", "delta_abs"), step("half_width_in", "delta_abs"))
stopifnot(nchar(alt) >= 40)
writeLines(alt, file.path(out_dir, "alt.txt"))
cat("wrote", file.path(out_dir, "zone-edges-three-periods.png"), "\n")
