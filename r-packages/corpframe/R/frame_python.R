# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

#' Find a working Python executable
#'
#' Checks common locations for a Python 3 binary with matplotlib available.
#'
#' @param python Explicit path to Python, or NULL for auto-detection.
#' @return The path to the Python executable.
#' @export
find_python <- function(python = NULL) {
  if (!is.null(python)) {
    if (!file.exists(python)) stop("Python not found at: ", python)
    return(python)
  }

  # Check R option: options(corpframe.python = "/path/to/python")
  opt_python <- getOption("corpframe.python", default = "")
  if (nzchar(opt_python)) {
    if (!file.exists(opt_python)) {
      stop("options(corpframe.python) is set to '", opt_python, "' but file not found")
    }
    return(opt_python)
  }

  # Check CORPFRAME_PYTHON env var
  env_python <- Sys.getenv("CORPFRAME_PYTHON", "")
  if (nzchar(env_python)) {
    if (!file.exists(env_python)) {
      stop("CORPFRAME_PYTHON is set to '", env_python, "' but file not found")
    }
    return(env_python)
  }

  # Check reticulate's Python (if reticulate is installed)
  if (requireNamespace("reticulate", quietly = TRUE)) {
    tryCatch({
      ret_python <- reticulate::py_config()$python
      if (!is.null(ret_python) && nzchar(ret_python) && file.exists(ret_python)) {
        return(ret_python)
      }
    }, error = function(e) NULL)
  }

  # Common locations
  common_paths <- c(
    "/usr/local/bin/python3",
    "/usr/bin/python3",
    "/opt/homebrew/bin/python3",
    Sys.which("python3"),
    Sys.which("python")
  )
  for (path in common_paths) {
    if (nzchar(path) && file.exists(path)) {
      return(path)
    }
  }

  # Fallback: system `which`
  for (cmd in c("python3", "python")) {
    path <- system2("which", cmd, stdout = TRUE, stderr = FALSE)
    if (length(path) > 0 && nzchar(path) && file.exists(path)) {
      return(path)
    }
  }

  stop(
    "No Python found. Options:\n",
    "  - Set options(corpframe.python = '/path/to/python')\n",
    "  - Set CORPFRAME_PYTHON env var\n",
    "  - Install Python 3 with corpframe: pip install corpframe\n",
    "  - Pass python argument directly: apply_frame(..., python = '/path/to/python')"
  )
}


#' Apply corporate frame to PNG bytes via Python subprocess
#'
#' @param png_bytes Raw vector of PNG image data.
#' @param title Header title.
#' @param subtitle Header subtitle.
#' @param footnotes Footer footnotes (left-aligned).
#' @param sources Footer sources (right-aligned).
#' @param dpi Output resolution.
#' @param python Path to Python executable (NULL for auto-detect).
#' @return Raw vector of the framed PNG image.
#' @keywords internal
.apply_frame <- function(png_bytes,
                         title = "",
                         subtitle = "",
                         footnotes = "",
                         sources = "",
                         dpi = 300L,
                         python = NULL) {
  python <- find_python(python)

  # Write input to temp file, call Python corpframe CLI, read output
  input_file <- tempfile(fileext = ".png")
  output_file <- tempfile(fileext = ".png")
  on.exit(unlink(c(input_file, output_file)), add = TRUE)

  writeBin(png_bytes, input_file)

  cmd <- paste(
    shQuote(python), "-m", "corpframe",
    "--input", shQuote(input_file),
    "--output", shQuote(output_file),
    "--title", shQuote(title),
    "--subtitle", shQuote(subtitle),
    "--footnotes", shQuote(footnotes),
    "--sources", shQuote(sources),
    "--dpi", as.character(dpi)
  )

  result <- system(cmd, intern = TRUE)
  status <- attr(result, "status")

  if (!is.null(status) && status != 0) {
    stop(
      "Corporate frame Python script failed (exit ", status, "):\n",
      paste(result, collapse = "\n")
    )
  }

  if (!file.exists(output_file)) {
    stop("Corporate frame output file not created. Python output:\n",
         paste(result, collapse = "\n"))
  }

  readBin(output_file, "raw", file.info(output_file)$size)
}


#' Apply corporate frame to PNG bytes
#'
#' Takes raw PNG bytes, calls Python/matplotlib to add a corporate header
#' (title, subtitle) and footer (footnotes, sources), returns framed PNG bytes.
#'
#' @inheritParams .apply_frame
#' @return Raw vector of the framed PNG image.
#' @export
apply_frame <- function(png_bytes,
                        title = "",
                        subtitle = "",
                        footnotes = "",
                        sources = "",
                        dpi = 300L,
                        python = NULL) {
  .apply_frame(
    png_bytes,
    title = title,
    subtitle = subtitle,
    footnotes = footnotes,
    sources = sources,
    dpi = dpi,
    python = python
  )
}
