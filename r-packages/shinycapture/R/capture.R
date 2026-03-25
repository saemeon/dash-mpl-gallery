# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

#' Capture a Plotly chart from the browser
#'
#' Triggers a browser-side capture of a \code{plotlyOutput} element using
#' \code{Plotly.toImage()} with exact pixel dimensions. The result is sent
#' back to R as a base64 string available via \code{input$<input_id>}.
#'
#' @param id The output ID of the \code{plotlyOutput} to capture.
#' @param strategy A \code{capture_strategy} object (default:
#'   \code{plotly_strategy()}).
#' @param input_id The Shiny input ID that will receive the base64 result.
#'   Defaults to \code{".shinycapture.<id>"}.
#' @param session The Shiny session object.
#' @return Invisibly, the \code{input_id} string. Use
#'   \code{observeEvent(input[[input_id]], ...)} to react to the capture.
#'
#' @examples
#' \dontrun{
#' server <- function(input, output, session) {
#'   output$my_plot <- plotly::renderPlotly({ ... })
#'
#'   observeEvent(input$capture_btn, {
#'     capture_plotly("my_plot",
#'       strategy = plotly_strategy(
#'         strip_title = TRUE,
#'         width = 2400, height = 1600
#'       )
#'     )
#'   })
#'
#'   observeEvent(input[[".shinycapture.my_plot"]], {
#'     bytes <- base64_decode(input[[".shinycapture.my_plot"]])
#'     # Process with magick, save, display, etc.
#'   })
#' }
#' }
#' @export
capture_plotly <- function(id,
                           strategy = plotly_strategy(),
                           input_id = NULL,
                           session = shiny::getDefaultReactiveDomain()) {
  if (is.null(input_id)) {
    input_id <- paste0(".shinycapture.", id)
  }

  .ensure_deps(session)

  session$sendCustomMessage("shinycapture-capture", list(
    id = session$ns(id),
    input_id = input_id,
    strategy = strategy$strategy,
    preprocess_js = strategy$preprocess_js,
    opts = strategy$opts
  ))

  invisible(input_id)
}

#' Capture an arbitrary HTML element from the browser
#'
#' Triggers a browser-side capture of any DOM element using html2canvas
#' (default) or another strategy.
#'
#' @inheritParams capture_plotly
#' @param strategy A \code{capture_strategy} object (default:
#'   \code{html2canvas_strategy()}).
#'
#' @export
capture_element <- function(id,
                            strategy = html2canvas_strategy(),
                            input_id = NULL,
                            session = shiny::getDefaultReactiveDomain()) {
  # Auto-include vendored html2canvas if using html2canvas strategy
  if (identical(strategy$strategy, "html2canvas")) {
    .ensure_html2canvas(session)
  }
  capture_plotly(id, strategy, input_id, session)
}


# Inject html2canvas JS once per session
.ensure_html2canvas <- function(session) {
  if (is.null(session$userData$.html2canvas_added) ||
      !session$userData$.html2canvas_added) {
    shiny::insertUI("head", "beforeEnd", immediate = TRUE,
                    ui = html2canvas_deps())
    session$userData$.html2canvas_added <- TRUE
  }
}


#' Batch-capture multiple elements
#'
#' Captures several elements in one call. Each element gets its own input ID
#' (defaults to \code{".shinycapture.<id>"}). Returns a named list of input IDs
#' keyed by element ID, so you can observe each result separately.
#'
#' @param ids Character vector of output IDs to capture.
#' @param strategies A single \code{capture_strategy} applied to all elements,
#'   or a named list of strategies keyed by element ID.
#' @param session The Shiny session object.
#' @return A named list of input IDs (keyed by element ID).
#'
#' @examples
#' \dontrun{
#' server <- function(input, output, session) {
#'   observeEvent(input$capture_all, {
#'     input_ids <- capture_batch(
#'       c("plot1", "plot2", "plot3"),
#'       strategies = plotly_strategy(strip_title = TRUE, width = 1200)
#'     )
#'   })
#'
#'   # Observe each result
#'   observeEvent(input[[".shinycapture.plot1"]], { ... })
#'   observeEvent(input[[".shinycapture.plot2"]], { ... })
#' }
#' }
#' @export
capture_batch <- function(ids,
                          strategies = plotly_strategy(),
                          session = shiny::getDefaultReactiveDomain()) {
  if (inherits(strategies, "capture_strategy")) {
    # Single strategy for all elements
    strat_list <- stats::setNames(
      rep(list(strategies), length(ids)),
      ids
    )
  } else if (is.list(strategies)) {
    # Named list: one strategy per element
    missing <- setdiff(ids, names(strategies))
    if (length(missing) > 0) {
      stop("Missing strategies for: ", paste(missing, collapse = ", "))
    }
    strat_list <- strategies
  } else {
    stop("strategies must be a capture_strategy or a named list of them")
  }

  input_ids <- character(length(ids))
  names(input_ids) <- ids

  for (id in ids) {
    input_ids[[id]] <- capture_plotly(
      id,
      strategy = strat_list[[id]],
      session = session
    )
  }

  invisible(input_ids)
}


# Inject JS dependencies once per session
.ensure_deps <- function(session) {
  if (is.null(session$userData$.shinycapture_added) ||
      !session$userData$.shinycapture_added) {
    shiny::insertUI("head", "beforeEnd", immediate = TRUE,
                    ui = shinycapture_deps())
    session$userData$.shinycapture_added <- TRUE
  }
}
