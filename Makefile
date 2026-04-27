# ==============================================================================
# Makefile — Distributed MPI Search Build System
# ==============================================================================
#
# Targets:
#   make          Build the optimized release binary
#   make debug    Build with debug symbols and assertions
#   make clean    Remove all build artifacts
#
# ==============================================================================

CXX       := mpicxx
CXXFLAGS  := -std=c++17 -Wall -Wextra -Wpedantic
OPT_FLAGS := -O3 -DNDEBUG
DBG_FLAGS := -g -O0 -DDEBUG

INCLUDE   := -Iinclude
SRC_DIR   := src
BUILD_DIR := build
TARGET    := distributed_search

SOURCES   := $(wildcard $(SRC_DIR)/*.cpp)
OBJECTS   := $(patsubst $(SRC_DIR)/%.cpp, $(BUILD_DIR)/%.o, $(SOURCES))
DBG_OBJS  := $(patsubst $(SRC_DIR)/%.cpp, $(BUILD_DIR)/debug_%.o, $(SOURCES))

# ==============================================================================
# Default target: optimized release build
# ==============================================================================
all: $(BUILD_DIR) $(TARGET)
	@echo "  ✓ Built $(TARGET) with -O3 optimization"

$(TARGET): $(OBJECTS)
	$(CXX) $(CXXFLAGS) $(OPT_FLAGS) $(INCLUDE) -o $@ $^

$(BUILD_DIR)/%.o: $(SRC_DIR)/%.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(OPT_FLAGS) $(INCLUDE) -c $< -o $@

# ==============================================================================
# Debug target: with debug symbols, no optimization
# ==============================================================================
debug: $(BUILD_DIR) $(TARGET)_debug
	@echo "  ✓ Built $(TARGET)_debug with debug symbols"

$(TARGET)_debug: $(DBG_OBJS)
	$(CXX) $(CXXFLAGS) $(DBG_FLAGS) $(INCLUDE) -o $@ $^

$(BUILD_DIR)/debug_%.o: $(SRC_DIR)/%.cpp | $(BUILD_DIR)
	$(CXX) $(CXXFLAGS) $(DBG_FLAGS) $(INCLUDE) -c $< -o $@

# ==============================================================================
# Utility targets
# ==============================================================================
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

clean:
	rm -rf $(BUILD_DIR) $(TARGET) $(TARGET)_debug

.PHONY: all debug clean
