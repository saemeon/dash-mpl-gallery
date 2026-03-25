# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

#' Decode a base64 data-URI or raw base64 string to raw bytes
#'
#' Strips the \code{data:image/...;base64,} prefix if present, then
#' decodes the remaining base64 payload to raw bytes.
#'
#' @param b64_string A base64-encoded string, optionally with data-URI prefix.
#' @return A \code{raw} vector containing the decoded bytes.
#' @export
base64_decode <- function(b64_string) {
  # Strip data-URI prefix if present
  if (grepl("^data:", b64_string)) {
    b64_string <- sub("^data:[^;]+;base64,", "", b64_string)
  }
  jsonlite::base64_dec(b64_string)
}

#' HTML dependency for shinycapture JS
#'
#' Returns an \code{htmltools::htmlDependency} that loads the
#' shinycapture JavaScript file. Called automatically by
#' \code{capture_plotly()} / \code{capture_element()}.
#'
#' @return An \code{htmlDependency} object.
#' @export
shinycapture_deps <- function() {
  htmltools::htmlDependency(
    name = "shinycapture",
    version = as.character(utils::packageVersion("shinycapture")),
    package = "shinycapture",
    src = "shinycapture",
    script = "shinycapture.js"
  )
}


#' HTML dependency for vendored html2canvas
#'
#' Returns an \code{htmltools::htmlDependency} that loads the vendored
#' html2canvas.min.js. Called automatically by \code{capture_element()} when
#' using \code{html2canvas_strategy()}.
#'
#' @return An \code{htmlDependency} object.
#' @export
html2canvas_deps <- function() {
  htmltools::htmlDependency(
    name = "html2canvas",
    version = "1.4.1",
    package = "shinycapture",
    src = "shinycapture",
    script = "html2canvas.min.js"
  )
}
