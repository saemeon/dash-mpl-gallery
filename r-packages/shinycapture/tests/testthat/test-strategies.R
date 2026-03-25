# Copyright (c) Simon Niederberger.
# Distributed under the terms of the MIT License.

# ---------------------------------------------------------------------------
# plotly_strategy
# ---------------------------------------------------------------------------

test_that("plotly_strategy returns correct class", {
  s <- plotly_strategy()
  expect_s3_class(s, "capture_strategy")
  expect_equal(s$strategy, "plotly")
})

test_that("plotly_strategy with no strips has NULL preprocess", {
  s <- plotly_strategy()
  expect_null(s$preprocess_js)
})

test_that("plotly_strategy strip_title generates title patch", {
  s <- plotly_strategy(strip_title = TRUE)
  expect_true(!is.null(s$preprocess_js))
  expect_true(grepl("title", s$preprocess_js))
  expect_true(grepl("margin", s$preprocess_js))
  expect_true(grepl("newPlot", s$preprocess_js))
})

test_that("plotly_strategy strip_legend generates showlegend patch", {
  s <- plotly_strategy(strip_legend = TRUE)
  expect_true(grepl("showlegend", s$preprocess_js))
})

test_that("plotly_strategy strip_margin generates margin patch", {
  s <- plotly_strategy(strip_margin = TRUE)
  expect_true(grepl("l:0", s$preprocess_js))
})

test_that("plotly_strategy strip_colorbar generates showscale patch", {
  s <- plotly_strategy(strip_colorbar = TRUE)
  expect_true(grepl("showscale", s$preprocess_js))
})

test_that("plotly_strategy strip_annotations generates annotations patch", {
  s <- plotly_strategy(strip_annotations = TRUE)
  expect_true(grepl("annotations", s$preprocess_js))
})

test_that("plotly_strategy strip_axis_titles generates axis patch", {
  s <- plotly_strategy(strip_axis_titles = TRUE)
  expect_true(grepl("xy", s$preprocess_js))
  expect_true(grepl("title", s$preprocess_js))
})

test_that("plotly_strategy all strips combined", {
  s <- plotly_strategy(
    strip_title = TRUE, strip_legend = TRUE,
    strip_annotations = TRUE, strip_axis_titles = TRUE,
    strip_colorbar = TRUE, strip_margin = TRUE
  )
  js <- s$preprocess_js
  expect_true(grepl("title", js))
  expect_true(grepl("showlegend", js))
  expect_true(grepl("annotations", js))
  expect_true(grepl("showscale", js))
  expect_true(grepl("l:0", js))
})

test_that("plotly_strategy width/height in opts", {
  s <- plotly_strategy(width = 2400, height = 1600)
  expect_equal(s$opts$width, 2400)
  expect_equal(s$opts$height, 1600)
  expect_equal(s$opts$format, "png")
})

test_that("plotly_strategy width in preprocess JS", {
  s <- plotly_strategy(strip_title = TRUE, width = 2400)
  expect_true(grepl("2400", s$preprocess_js))
})

test_that("plotly_strategy height in preprocess JS uses offsetHeight when NULL", {
  s <- plotly_strategy(strip_title = TRUE, height = NULL)
  expect_true(grepl("offsetHeight", s$preprocess_js))
})

test_that("plotly_strategy width in preprocess JS uses offsetWidth when NULL", {
  s <- plotly_strategy(strip_title = TRUE, width = NULL)
  expect_true(grepl("offsetWidth", s$preprocess_js))
})

# ---------------------------------------------------------------------------
# Format selection
# ---------------------------------------------------------------------------

test_that("plotly_strategy default format is png", {
  s <- plotly_strategy()
  expect_equal(s$opts$format, "png")
})

test_that("plotly_strategy format jpeg", {
  s <- plotly_strategy(format = "jpeg")
  expect_equal(s$opts$format, "jpeg")
})

test_that("plotly_strategy format webp", {
  s <- plotly_strategy(format = "webp")
  expect_equal(s$opts$format, "webp")
})

test_that("plotly_strategy format svg", {
  s <- plotly_strategy(format = "svg")
  expect_equal(s$opts$format, "svg")
})

test_that("html2canvas_strategy default format is png", {
  s <- html2canvas_strategy()
  expect_equal(s$opts$format, "png")
})

test_that("html2canvas_strategy format jpeg", {
  s <- html2canvas_strategy(format = "jpeg")
  expect_equal(s$opts$format, "jpeg")
})

# ---------------------------------------------------------------------------
# html2canvas_strategy
# ---------------------------------------------------------------------------

test_that("html2canvas_strategy returns correct class", {
  s <- html2canvas_strategy()
  expect_s3_class(s, "capture_strategy")
  expect_equal(s$strategy, "html2canvas")
  expect_null(s$preprocess_js)
})

test_that("html2canvas_strategy scale option", {
  s <- html2canvas_strategy(scale = 3)
  expect_equal(s$opts$scale, 3)
})

test_that("html2canvas_strategy default scale is 2", {
  s <- html2canvas_strategy()
  expect_equal(s$opts$scale, 2)
})
