# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

#' Render ggplot with corporate frame and display
#'
#' Internal helper: renders ggplot to PNG, applies frame via Python,
#' then displays using the best available method.
#'
#' @param plot A ggplot2 object (plain, without corporate_framed_gg class).
#' @param params List of frame parameters (title, subtitle, etc.).
#' @keywords internal
.render_framed <- function(plot, params) {
  # Render ggplot to temp PNG
  tmp_in <- tempfile(fileext = ".png")
  on.exit(unlink(tmp_in), add = TRUE)

  width <- params$width %||% 8
  height <- params$height %||% 5
  dpi <- params$dpi %||% 300L

  ggplot2::ggsave(tmp_in, plot = plot, width = width, height = height,
                  dpi = dpi, device = "png")

  png_bytes <- readBin(tmp_in, "raw", file.info(tmp_in)$size)

  # Apply corporate frame via Python
  framed <- apply_frame(
    png_bytes,
    title = params$title %||% "",
    subtitle = params$subtitle %||% "",
    footnotes = params$footnotes %||% "",
    sources = params$sources %||% "",
    dpi = dpi,
    python = params$python
  )

  # Write framed PNG
  tmp_out <- tempfile(fileext = ".png")
  writeBin(framed, tmp_out)

  if (requireNamespace("png", quietly = TRUE)) {
    # Plots pane — also works inside ggsave()
    img <- png::readPNG(tmp_out)
    grid::grid.newpage()
    grid::grid.raster(img)
  } else {
    # Viewer fallback — no png package needed
    tmp_b64 <- tempfile(fileext = ".b64")
    on.exit(unlink(tmp_b64), add = TRUE)
    system2("base64", c("-i", shQuote(tmp_out), "-o", shQuote(tmp_b64)))
    b64 <- paste(readLines(tmp_b64, warn = FALSE), collapse = "")

    tmp_html <- tempfile(fileext = ".html")
    writeLines(sprintf(
      '<html><body style="margin:0;background:#fff"><img src="data:image/png;base64,%s" style="max-width:100%%"></body></html>',
      b64
    ), tmp_html)
    viewer <- getOption("viewer", utils::browseURL)
    viewer(tmp_html)
  }
}


#' Add a corporate frame to a ggplot
#'
#' Use with \code{+} to attach corporate frame parameters to a ggplot.
#' The frame is only applied at print time, so it can be added at any
#' position in the ggplot pipeline. Additional layers added after
#' \code{corporate_frame()} work normally.
#'
#' Works with \code{print()} and interactive display in RStudio.
#' When the \pkg{png} package is installed, also works with
#' \code{ggsave()} and displays in the Plots pane.
#'
#' @param title Header title. If NULL (default), uses \code{labs(title = ...)}
#'   from the ggplot.
#' @param subtitle Header subtitle. If NULL (default), uses
#'   \code{labs(subtitle = ...)} from the ggplot.
#' @param footnotes Footer text, left-aligned.
#' @param sources Footer text, right-aligned.
#' @param width Plot width in inches (default 8).
#' @param height Plot height in inches (default 5).
#' @param dpi Resolution in DPI (default 300).
#' @param python Path to Python executable (NULL for auto-detect).
#' @return An object that can be added to a ggplot with \code{+}.
#'
#' @examples
#' \dontrun{
#' library(ggplot2)
#'
#' # Title from labs() — just add corporate_frame():
#' ggplot(mtcars, aes(wt, mpg)) + geom_point() +
#'   labs(title = "Weight vs MPG", subtitle = "mtcars") +
#'   corporate_frame()
#'
#' # Or set title directly:
#' ggplot(mtcars, aes(wt, mpg)) + geom_point() +
#'   corporate_frame(title = "Weight vs MPG")
#'
#' # Explicit title overrides labs():
#' ggplot(mtcars, aes(wt, mpg)) + geom_point() +
#'   labs(title = "Ignored") +
#'   corporate_frame(title = "This wins")
#' }
#' @export
corporate_frame <- function(title = NULL,
                            subtitle = NULL,
                            footnotes = "",
                            sources = "",
                            width = 8,
                            height = 5,
                            dpi = 300L,
                            python = NULL) {
  params <- list(
    title = title,
    subtitle = subtitle,
    footnotes = footnotes,
    sources = sources,
    width = width,
    height = height,
    dpi = dpi,
    python = python
  )
  structure(params, class = "corporate_frame_params")
}


#' @export
ggplot_add.corporate_frame_params <- function(object, plot, object_name) {
  attr(plot, "corporate_frame") <- object
  class(plot) <- c("corporate_framed_gg", class(plot))
  # Apply a complete theme to fix RStudio Environment display,
  # then re-apply user's theme so it isn't lost
  saved_theme <- plot$theme
  plot <- plot + ggplot2::theme_get()
  if (length(saved_theme) > 0) {
    plot <- plot + saved_theme
  }
  plot
}


#' @export
print.corporate_framed_gg <- function(x, ...) {
  params <- attr(x, "corporate_frame")

  # Strip wrapper so rendering sees a plain ggplot
  class(x) <- setdiff(class(x), "corporate_framed_gg")
  attr(x, "corporate_frame") <- NULL

  # Pull title/subtitle from labs() if not set in corporate_frame()
  if (is.null(params$title)) {
    params$title <- x$labels$title %||% ""
    x$labels$title <- NULL
  } else if (!is.null(x$labels$title)) {
    warning("Both labs(title) and corporate_frame(title) are set; ",
            "both will be rendered.", call. = FALSE)
  }
  if (is.null(params$subtitle)) {
    params$subtitle <- x$labels$subtitle %||% ""
    x$labels$subtitle <- NULL
  } else if (!is.null(x$labels$subtitle)) {
    warning("Both labs(subtitle) and corporate_frame(subtitle) are set; ",
            "both will be rendered.", call. = FALSE)
  }

  .render_framed(x, params)

  invisible(x)
}
