# The R chokepoint. Every idiom the linter knows appears here on purpose.
library(httr2)
library(curl)
absump_http_get <- function(u, dest) {
  resp <- httr2::request(u) |> req_perform()
  download.file(u, destfile = dest)
  httr::GET(u)
  txt <- readLines(url(u))
  out <- system2("curl", c("-s", u), stdout = TRUE)
  invisible(list(resp, txt, out))
}
