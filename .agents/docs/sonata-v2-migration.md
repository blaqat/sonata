# Sonata v2 Migration

The goal of this migration is to rewrite sonata from scratching following the Managers v2 Epic.
This effectively is a new project working off the backbone of the old sonata.
The rewrite will happen in this order

0. Project Setup / Depdency Updates - we are able to now take a step back and update dependecies or choose new better fitting ones
1. Core Managers - S26-09 Manager v2 epic tickets
2. Updating Prompts - `@blaqat` will do this
3. Writing Tests - Done at the end of S26-09, no tickets for this are made yet until we know what we have
4. Porting Plugins - S26-10 Manager v2 epic tickets

You will be able and encouraged to reference sonata-v1 in `.src.old/`

## Features for the rewrite

- We will diverge off the normal path for creating features here
- All new features will be in `feature/SONA-XXX-ShortenedTitle` -> `sonata-v2` instead of to `testing` or `main`
- There will be NO tests written until the Core Rewrite is complete as core rewrite will include managers to help with testing such as the TestClient
- We will resume the testing flow once the bot is able to run again around step 3. Porting Plugins

## Code Style

- Code style will be very strictly enforced
- Code should be highly readable in optimized for cyclomatic complexity.
    - Devs should not have to jump around the codebase to understand what is going on
    - Meaning, there should not be many helper functions if they are not necessary / only used once
    - Write code inline declarative
    - Use clear and descriptive variable names, no need to shorten
    - Have comments throughout the code if in longer functions to explain even simple thing unless it is clearly read from the variable names
- File/Namespacing/Grouping Style
    - Data Types and Functions are Strictly separated. Data types are independent of functions.
    - Composition / Data Embedding over Inheritance
    - Modularity: modules are large grouping code organically by feature isntead of broken into tiny objects prematurely
    - Logic modules never talk to state modules
