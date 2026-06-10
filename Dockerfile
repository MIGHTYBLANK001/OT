FROM tsl0922/ttyd:alpine
EXPOSE 7681
CMD ["ttyd", "-W", "bash"]
