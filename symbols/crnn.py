import mxnet as mx
from fit.ctc_loss import add_ctc_loss
from fit.lstm import lstm

def crnn_no_lstm(hp):

    # input
    data = mx.sym.Variable('data')
    label = mx.sym.Variable('label')

    kernel_size = [(3, 3), (3, 3), (3, 3), (3, 3), (3, 3), (3, 3)]
    padding_size = [(1, 1), (1, 1), (1, 1), (1, 1), (1, 1), (1, 1)]
    layer_size = [min(32*2**(i+1), 512) for i in range(len(kernel_size))]

    def convRelu(i, input_data, bn=True):
        layer = mx.symbol.Convolution(name='conv-%d' % i, data=input_data, kernel=kernel_size[i], pad=padding_size[i],
                                      num_filter=layer_size[i])
        if bn:
            layer = mx.sym.BatchNorm(data=layer, name='batchnorm-%d' % i)
        layer = mx.sym.LeakyReLU(data=layer,name='leakyrelu-%d' % i)
        return layer

    net = convRelu(0, data) # bz x f x 32 x 200
    max = mx.sym.Pooling(data=net, name='pool-0_m', pool_type='max', kernel=(2, 2), stride=(2, 2))
    avg = mx.sym.Pooling(data=net, name='pool-0_a', pool_type='avg', kernel=(2, 2), stride=(2, 2))
    net = max - avg  # 16 x 100
    net = convRelu(1, net)
    net = mx.sym.Pooling(data=net, name='pool-1', pool_type='max', kernel=(2, 2), stride=(2, 2)) # bz x f x 8 x 50
    net = convRelu(2, net, True)
    net = convRelu(3, net)
    net = mx.sym.Pooling(data=net, name='pool-2', pool_type='max', kernel=(2, 2), stride=(2, 2)) # bz x f x 4 x 25
    net = convRelu(4, net, True)
    net = convRelu(5, net)
    net = mx.symbol.Pooling(data=net, kernel=(4, 1), pool_type='avg', name='pool1') # bz x f x 1 x 25

    if hp.dropout > 0:
        net = mx.symbol.Dropout(data=net, p=hp.dropout)

    net = mx.sym.transpose(data=net, axes=[1,0,2,3])  # f x bz x 1 x 25
    net = mx.sym.flatten(data=net) # f x (bz x 25)
    hidden_concat = mx.sym.transpose(data=net, axes=[1,0]) # (bz x 25) x f

    # mx.sym.transpose(net, [])
    pred = mx.sym.FullyConnected(data=hidden_concat, num_hidden=hp.num_classes) # (bz x 25) x num_classes

    if hp.loss_type:
        # Training mode, add loss
        return add_ctc_loss(pred, hp.seq_length, hp.num_label, hp.loss_type)
    else:
        # Inference mode, add softmax
        return mx.sym.softmax(data=pred, name='softmax')

def crnn_lstm(hp):

    data = mx.sym.Variable('data')

    kernel_size = [(3, 3), (3, 3), (3, 3), (3, 3), (3, 3), (3, 3)]
    padding_size = [(1, 1), (1, 1), (1, 1), (1, 1), (1, 1), (1, 1)]
    layer_size = [64, 128, 256, 512, 512, 512]
    # layer_size = [min(32*2**(i+1), 512) for i in range(len(kernel_size))]

    def convRelu(i, input_data, bn=True, dw=False):
        layer = mx.symbol.Convolution(name='conv-%d' % i, data=input_data, kernel=kernel_size[i], pad=padding_size[i],
                                      num_filter=layer_size[i-1] if dw else layer_size[i], num_group= layer_size[i-1] if dw else 1)
        # if bn:
        layer = mx.sym.BatchNorm(data=layer, name='batchnorm-%d' % i, fix_gamma=False)
        layer = mx.sym.LeakyReLU(data=layer, name='leakyrelu-%d' % i)
        # if dw and layer_size[i] != layer_size[i-1]:
        #     layer = mx.symbol.Convolution(name='conv-%d-1x1' % i, data=layer, kernel=(1, 1), pad=(0, 0),
        #                                   num_filter=layer_size[i])
        #     #if bn:
        #     layer = mx.sym.BatchNorm(data=layer, name='batchnorm-%d-1x1' % i)
        #     layer = mx.sym.LeakyReLU(data=layer, name='leakyrelu-%d-1x1' % i)
        return layer

    net = convRelu(0, data) # bz x 64 x 32 x 200
    # max = mx.sym.Pooling(data=net, name='pool-0_m', pool_type='max', kernel=(2, 2), stride=(2, 2))
    # avg = mx.sym.Pooling(data=net, name='pool-0_a', pool_type='avg', kernel=(2, 2), stride=(2, 2))
    # net = max - avg  # 16 x 100
    net = mx.sym.Pooling(data=net, name='pool-0', pool_type='max', kernel=(2, 2), stride=(2, 2)) # bz x 64 x 16 x 100
    net = convRelu(1, net, True, False) # bz x 128 x 16 x 100
    net = mx.sym.Pooling(data=net, name='pool-1', pool_type='max', kernel=(2, 2), stride=(2, 2)) # bz x 128 x 8 x 50
    net = convRelu(2, net, True, False) # bz x 256 x 8 x 50
    net = convRelu(3, net, True, False) # bz x 512 x 8 x 50
    net = mx.sym.Pooling(data=net, name='pool-2', pool_type='max', kernel=(2, 2), stride=(2, 2)) # bz x 512 x 4 x 25
    net = convRelu(4, net, True, False) # bz x 512 x 4 x 25
    net = convRelu(5, net, True, False) # bz x 512 x 4 x 25
    net = mx.symbol.Pooling(data=net, kernel=(4, 1), pool_type='avg', name='pool1') # bz x 512 x 1 x 25

    if hp.dropout > 0:
        net = mx.symbol.Dropout(data=net, p=hp.dropout)

    hidden_concat = lstm(net,num_lstm_layer=hp.num_lstm_layer, num_hidden=hp.num_hidden, seq_length=hp.seq_length)

    pred = mx.sym.FullyConnected(data=hidden_concat, num_hidden=hp.num_classes) # (bz x 25) x num_classes

    if hp.loss_type:
        # Training mode, add loss
        return add_ctc_loss(pred, hp.seq_length, hp.num_label, hp.loss_type)
    else:
        # Inference mode, add softmax
        return mx.sym.softmax(data=pred, name='softmax')


from hyperparams.hyperparams import hp

if __name__ == '__main__':
    #hp = Hyperparams()

    init_states = {}
    init_states['data'] = (hp.batch_size, 1, hp.img_height, hp.img_width)
    init_states['label'] = (hp.batch_size, hp.num_label)

    # init_c = {('l%d_init_c' % l): (hp.batch_size, hp.num_hidden) for l in range(hp.num_lstm_layer*2)}
    # init_h = {('l%d_init_h' % l): (hp.batch_size, hp.num_hidden) for l in range(hp.num_lstm_layer*2)}
    #
    # for item in init_c:
    #     init_states[item] = init_c[item]
    # for item in init_h:
    #     init_states[item] = init_h[item]

    symbol = crnn_no_lstm(hp)
    interals = symbol.get_internals()
    _, out_shapes, _ = interals.infer_shape(**init_states)
    shape_dict = dict(zip(interals.list_outputs(), out_shapes))

    for item in shape_dict:
        print(item,shape_dict[item])


