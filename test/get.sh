#!/usr/bin/env bash

wget -O - https://android.googlesource.com/platform/system/core/+/master/rootdir/init.rc?format=TEXT | base64 --decode > init.aosp.rc
