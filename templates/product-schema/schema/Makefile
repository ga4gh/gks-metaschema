SOURCE_DIRS := $(sort $(dir $(shell find . -type f -name '*-source.yaml' ! -path '*/import/*')))

.PHONY: all clean

all:
	@for source_dir in $(SOURCE_DIRS); do $(MAKE) -C $$source_dir all; done

clean:
	@for source_dir in $(SOURCE_DIRS); do $(MAKE) -C $$source_dir clean; done
