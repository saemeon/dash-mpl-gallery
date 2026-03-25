# corporate_frame() demo — run interactively in RStudio

options(corpframe.python = paste0(Sys.getenv("HOME"), "/corpframe-venv/bin/python3"))
library(corpframe)
library(ggplot2)

# 1. Title from labs() — most idiomatic
ggplot(mtcars, aes(wt, mpg, color = factor(cyl))) +
  geom_point(size = 3) +
  theme_minimal() +
  labs(title = "Weight vs Fuel Efficiency", subtitle = "mtcars dataset") +
  corporate_frame(dpi = 150)

# 2. Title directly in corporate_frame()
ggplot(mtcars, aes(wt, mpg, color = factor(cyl))) +
  geom_point(size = 3) +
  theme_minimal() +
  corporate_frame(title = "Weight vs Fuel Efficiency", dpi = 150)

# 3. Order doesn't matter
ggplot(mtcars, aes(wt, mpg)) +
  corporate_frame(dpi = 150) +
  geom_point(aes(color = factor(cyl)), size = 3) +
  labs(title = "Added in the middle") +
  theme_minimal()

# 4. ggsave works
p <- ggplot(mtcars, aes(factor(cyl), mpg)) +
  geom_boxplot() +
  theme_minimal() +
  labs(title = "MPG by Cylinder Count") +
  corporate_frame(dpi = 150)

ggsave("/tmp/corpframe_test.png", p)
