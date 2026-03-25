# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

# ---------------------------------------------------------------------------
# capture_batch (unit tests — no Shiny session required)
# ---------------------------------------------------------------------------

test_that("capture_batch rejects non-strategy strategies arg", {
  # Mock session to avoid Shiny dep
  mock_session <- list(
    ns = identity,
    userData = list(.shinycapture_added = TRUE),
    sendCustomMessage = function(...) {}
  )

  expect_error(
    capture_batch(c("a", "b"), strategies = "not_a_strategy", session = mock_session),
    "capture_strategy"
  )
})

test_that("capture_batch errors on missing strategies for named list", {
  mock_session <- list(
    ns = identity,
    userData = list(.shinycapture_added = TRUE),
    sendCustomMessage = function(...) {}
  )

  expect_error(
    capture_batch(
      c("a", "b"),
      strategies = list(a = plotly_strategy()),
      session = mock_session
    ),
    "Missing strategies for: b"
  )
})

test_that("capture_batch with single strategy sends messages for all ids", {
  messages <- list()
  mock_session <- list(
    ns = identity,
    userData = list(.shinycapture_added = TRUE),
    sendCustomMessage = function(type, data) {
      messages[[length(messages) + 1]] <<- data
    }
  )

  result <- capture_batch(
    c("plot1", "plot2", "plot3"),
    strategies = plotly_strategy(width = 1200),
    session = mock_session
  )

  expect_equal(length(messages), 3)
  expect_equal(messages[[1]]$id, "plot1")
  expect_equal(messages[[2]]$id, "plot2")
  expect_equal(messages[[3]]$id, "plot3")
  expect_equal(messages[[1]]$opts$width, 1200)

  expect_equal(result[["plot1"]], ".shinycapture.plot1")
  expect_equal(result[["plot2"]], ".shinycapture.plot2")
  expect_equal(result[["plot3"]], ".shinycapture.plot3")
})

test_that("capture_batch with named strategy list uses per-element strategies", {
  messages <- list()
  mock_session <- list(
    ns = identity,
    userData = list(.shinycapture_added = TRUE),
    sendCustomMessage = function(type, data) {
      messages[[length(messages) + 1]] <<- data
    }
  )

  result <- capture_batch(
    c("a", "b"),
    strategies = list(
      a = plotly_strategy(width = 800),
      b = plotly_strategy(width = 1600, format = "svg")
    ),
    session = mock_session
  )

  expect_equal(length(messages), 2)
  expect_equal(messages[[1]]$opts$width, 800)
  expect_equal(messages[[2]]$opts$width, 1600)
  expect_equal(messages[[2]]$opts$format, "svg")
})
